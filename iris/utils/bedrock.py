# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import logging
import json
import boto3
import tiktoken
from .cache_metrics import get_cache_metrics

log = logging.getLogger(__name__)

# Global tokenizer instance for efficient reuse
_encoding = None


def _get_encoding():
    """Get or initialize the tiktoken encoding."""
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


prompt_caching_base_models = [
    "anthropic.claude-opus-4-5-20251101-v1:0",
    "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
    "anthropic.claude-opus-4-1-20250805-v1:0",
    "anthropic.claude-opus-4-20250514-v1:0",
    "anthropic.claude-sonnet-4-20250514-v1:0",
    "anthropic.claude-3-7-sonnet-20250219-v1:0",
    "anthropic.claude-3-5-haiku-20241022-v1:0",
    # 'anthropic.claude-3-5-sonnet-20241022-v2:0', # available in preview only
    "amazon.nova-micro-v1:0",
    "amazon.nova-lite-v1:0",
    "amazon.nova-pro-v1:0",
    "amazon.nova-premier-v1:0",
]

# Models supporting 1-hour TTL
extended_ttl_base_models = [
    "anthropic.claude-opus-4-5-20251101-v1:0",
    "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
]

region_prefixes = ["us.", "eu.", "apac."]
prompt_caching_models = prompt_caching_base_models.copy()
extended_ttl_models = extended_ttl_base_models.copy()
for prefix in region_prefixes:
    prompt_caching_models += [prefix + model for model in prompt_caching_base_models]
    extended_ttl_models += [prefix + model for model in extended_ttl_base_models]

# Minimum tokens per cache checkpoint by model
MIN_CACHE_TOKENS = {
    "claude-opus-4-5": 4096,
    "claude-haiku-4-5": 4096,
    "claude-3-5-haiku": 2048,
    "claude-sonnet-4-5": 1024,
    "claude-opus-4-1": 1024,
    "claude-opus-4-20250514": 1024,
    "claude-sonnet-4-20250514": 1024,
    "claude-3-7-sonnet": 1024,
    "nova-micro": 1000,
    "nova-lite": 1000,
    "nova-pro": 1000,
    "nova-premier": 1000,
}


def get_min_cache_tokens(model_id: str) -> int:
    """Get minimum tokens required for caching for a given model."""
    for key, min_tokens in MIN_CACHE_TOKENS.items():
        if key in model_id:
            return min_tokens
    return 1024


def estimate_tokens(text: str) -> int:
    """Estimate tokens using tiktoken (approximates Claude tokenization)."""
    encoding = _get_encoding()
    return len(encoding.encode(text))


def call_bedrock_streaming_helper(
    model_id,
    bedrock_client,
    messages,
    system,
    response_text_only=True,
    maxTokens=4096,
):
    """Helper function to handle streaming responses"""
    stream_response = bedrock_client.converse_stream(
        modelId=model_id,
        messages=messages,
        system=system,
        inferenceConfig={
            "maxTokens": maxTokens,
        },
    )

    text_content = ""
    # keep the response interface the same
    # copy contents of response except stream
    response = {k: v for k, v in stream_response.items() if k != "stream"}
    response["output"] = {"message": {}}

    for event in stream_response.get("stream"):
        if "messageStart" in event:
            response["output"]["message"]["role"] = event["messageStart"]["role"]
        if "contentBlockDelta" in event:
            text_content += event["contentBlockDelta"]["delta"]["text"]
            yield (event["contentBlockDelta"]["delta"]["text"])
        if "messageStop" in event:
            response["stopReason"] = event["messageStop"]["stopReason"]
        if "metadata" in event:
            metadata = event["metadata"]
            response["output"].update(metadata)
            if "usage" in metadata:
                log.debug(f"INPUT TOKENS: {metadata['usage']['inputTokens']}")
                log.debug(f"OUTPUT TOKENS: {metadata['usage']['outputTokens']}")
                if model_id in prompt_caching_models:
                    cache_read_tokens = metadata["usage"].get(
                        "cacheReadInputTokens", -1
                    )
                    cache_write_tokens = metadata["usage"].get(
                        "cacheWriteInputTokens", -1
                    )
                    log.debug(f"CACHE READ INPUT TOKENS: {cache_read_tokens}")
                    log.debug(f"CACHE WRITE INPUT TOKENS: {cache_write_tokens}")

                    # Record cache metrics
                    response["usage"] = metadata["usage"]
                    get_cache_metrics().record_response(response)
    response["output"]["message"]["content"] = [{"text": text_content}]

    if response_text_only:
        final_response = text_content
    else:
        final_response = response["output"]["message"]
    return final_response


def call_bedrock(
    model_id,
    bedrock_client,
    system_message=None,
    static_message=None,
    dynamic_message=None,
    conversation_history=[],
    user_query=None,
    response_text_only=True,
    maxTokens=4096,
    streaming=False,
    cache_ttl="5m",
):
    content = []
    if static_message or dynamic_message:
        if static_message and str(static_message).strip():
            if model_id in prompt_caching_models:
                estimated_tokens = estimate_tokens(static_message)
                min_tokens = get_min_cache_tokens(model_id)

                if estimated_tokens >= min_tokens:
                    cache_point = {"type": "default"}
                    if cache_ttl == "1h" and model_id in extended_ttl_models:
                        cache_point["ttl"] = "1h"
                    content = content + [
                        {"text": static_message},
                        {"cachePoint": cache_point},
                    ]
                else:
                    log.debug(
                        f"Static message ({estimated_tokens} tokens) below minimum ({min_tokens}) for caching"
                    )
                    content.append({"text": static_message})
            else:
                content.append({"text": static_message})
        if dynamic_message and str(dynamic_message).strip():
            content.append({"text": dynamic_message})
        messages = [{"role": "user", "content": content}] if content else []
    else:
        messages = []

    if conversation_history:
        messages = messages + conversation_history

    if user_query:
        messages.append({"role": "user", "content": [{"text": user_query}]})

    system = [{"text": system_message}]

    log.debug(f"MESSAGES: {json.dumps(messages, indent=2)}")
    log.debug(f"SYSTEM: {json.dumps(system, indent=2)}")

    if not streaming:
        raw_response = bedrock_client.converse(
            modelId=model_id,
            messages=messages,
            system=system,
            inferenceConfig={
                "maxTokens": maxTokens,
            },
        )

        if response_text_only:
            response = raw_response["output"]["message"]["content"][0]["text"]
        else:
            response = raw_response["output"]["message"]

        input_tokens = raw_response["usage"]["inputTokens"]
        output_tokens = raw_response["usage"]["outputTokens"]
        log.debug(f"INPUT TOKENS: {input_tokens}")
        log.debug(f"OUTPUT TOKENS: {output_tokens}")

        if model_id in prompt_caching_models:
            if "usage" in raw_response:
                cache_read_tokens = raw_response["usage"].get(
                    "cacheReadInputTokens", -1
                )
                cache_write_tokens = raw_response["usage"].get(
                    "cacheWriteInputTokens", -1
                )
                log.debug(f"CACHE READ INPUT TOKENS: {cache_read_tokens}")
                log.debug(f"CACHE WRITE INPUT TOKENS: {cache_write_tokens}")

                # Record cache metrics
                get_cache_metrics().record_response(raw_response)

        return response
    else:
        # Use the streaming helper function which returns a generator
        return call_bedrock_streaming_helper(
            model_id=model_id,
            bedrock_client=bedrock_client,
            messages=messages,
            system=system,
            response_text_only=response_text_only,
            maxTokens=maxTokens,
        )


def create_session_with_assumed_role(role_arn):
    """Create a boto3 session with assumed role"""
    sts_client = boto3.client("sts")

    assumed_role_object = sts_client.assume_role(
        RoleArn=role_arn, RoleSessionName="CrossAccountSession"
    )

    credentials = assumed_role_object["Credentials"]

    session = boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name="us-east-1",
    )

    return session
