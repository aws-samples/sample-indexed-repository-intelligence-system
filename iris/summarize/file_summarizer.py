# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import boto3
import re
import time
import logging
import threading
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor
from botocore.config import Config
from tqdm import tqdm

from ..utils.validation import validate_llm_model_access
from .utils import load_prompts, update_and_save_codebase_overview
from ..file_system.file_utils import hash_file_content, read_source
from ..utils import load_default_config
from ..utils.bedrock import call_bedrock

log = logging.getLogger(__name__)


_DEFAULT_CONFIG = load_default_config()
_DEFAULT_PROMPTS = load_prompts()


def monitor_progress(futures, counter, total_files, desc="📝 Summarizing files"):
    """Monitor and display progress of file processing."""
    with tqdm(total=total_files, desc=desc, unit="file") as pbar:
        last_completed = 0

        while any(not future.done() for future in futures):
            with counter["lock"]:
                current_completed = counter["completed"]

            # Update progress if more files completed
            if current_completed > last_completed:
                processed = current_completed - last_completed
                pbar.update(processed)
                last_completed = current_completed
            # Check more frequently
            time.sleep(1)  # nosemgrep

        # Final update to ensure we're at 100%
        with counter["lock"]:
            final_completed = counter["completed"]
        if final_completed > last_completed:
            pbar.update(final_completed - last_completed)


def process_file_queue(
    file_queue,
    model_config,
    results,
    counter,
    codebase_dir,
    output_dir,
    static_message,
    system_message,
):
    """Worker function that processes files from the queue using the given model configuration."""
    model_id = model_config["model_id"]
    region = model_config["region"]
    boto3_config = Config(
        region_name=region,
        read_timeout=300,  # Read timeout in seconds (5 minutes)
        retries={
            "mode": "standard",
            "max_attempts": 20,
        },  # Auto-retry configuration
    )
    bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

    # Create a simple entry for files that couldn't be read (None) or are empty
    empty_file_result = {
        "purpose": "Couldn't be read or is empty",
        "genai_system": "No",
        "has_bugs": "No bugs",
        "imported_files": [],
        "classes": {},
        "functions": {},
    }

    # Define max retries
    MAX_RETRIES = 1

    while True:
        # Get the next file from the queue, or None if queue is empty
        with counter["lock"]:
            if not file_queue:
                # No more files to process
                break
            path = file_queue.pop(0)
            # Get current retry count from the shared dictionary
            retry_count = counter["retry_counts"].get(path, 0)

        log.debug(f"FILE PATH: {path} -> Model: {model_id} Region: {region}")

        src_str = read_source(Path(path), codebase_dir=codebase_dir)

        if src_str is None or not src_str.strip():
            # Store the result and update the counter
            with counter["lock"]:
                results[path] = empty_file_result
                counter["completed"] += 1

                file_hash = hash_file_content(Path(codebase_dir) / Path(path))

                # Save both summary and hash atomically
                update_and_save_codebase_overview(
                    output_dir, {path: empty_file_result}, {path: file_hash}
                )

            continue

        dynamic_message = f"""
<file_path>
{path}
</file_path>

<file_content>
{src_str}
</file_content>
        """

        try:
            response = call_bedrock(
                static_message=static_message,
                dynamic_message=dynamic_message,
                system_message=system_message,
                model_id=model_id,
                bedrock_client=bedrock_client,
                maxTokens=32768,
            )
        except Exception as e:
            log.error(
                f"call_bedrock failed for file {path}\n"
                + f"Model: {model_id}\n"
                + f"Region: {region}\n"
                + f"src_str type: {type(src_str)}\n"
                + f"src_str value: {repr(src_str)}\n"
                + f"dynamic_message length: {len(dynamic_message)}\n"
                + f"static_message length: {len(static_message)}\n"
                + f"Error: {type(e).__name__}: {str(e)}"
            )
            # Skip this file and continue processing
            with counter["lock"]:
                counter["completed"] += 1
            continue

        try:
            pattern = r"```json\s*(.*)\s*```"
            result = re.search(pattern, response, flags=re.DOTALL).group(1)
            result = json.loads(result)

        except Exception as e:
            retry_count += 1
            log.debug(f"Raw response for file {path}: {response}")
            if retry_count <= MAX_RETRIES:
                with counter["lock"]:
                    counter["retry_counts"][path] = retry_count
                    file_queue.insert(1, path)  # Put back in queue at index 1
                log.warning(
                    f"Error processing file {path} (attempt {retry_count}/{MAX_RETRIES + 1}): {e}"
                )
            else:
                log.error(
                    f"Failed to process file {path} (attempt {retry_count}/{MAX_RETRIES + 1}) - skipping it: {e}"
                )
                result = empty_file_result

        # Store the result and update the counter
        with counter["lock"]:
            results[path] = result
            counter["completed"] += 1
            file_hash = hash_file_content(Path(codebase_dir) / Path(path))

            # Save both summary and hash atomically
            update_and_save_codebase_overview(
                output_dir, {path: result}, {path: file_hash}
            )


def summarize_files(
    files_to_summarize,
    codebase_dir,
    output_dir,
    models=None,
    prompts=None,
    additional_context="",
) -> dict:
    """
    Summarize a list of files using parallel processing.
    Will update codebase_overview.json

    Args:
        files_to_summarize: List of file paths to summarize
        codebase_dir: Root directory of codebase (defaults to config)
        output_dir: Output directory for results (defaults to config)
        models: List of model configs for parallel processing (defaults to config)
        prompts: Dict of prompt templates (defaults to loaded prompts)
        additional_context: Optional user-provided context for summarization

    Returns:
        Dict of file_path -> summary results
    """
    if not files_to_summarize:
        return {}

    if models is None:
        models = _DEFAULT_CONFIG["model_configuration"]["file_summarizer"]["models"]
        validate_llm_model_access(models)

    if prompts is None:
        prompts = _DEFAULT_PROMPTS

    num_models = len(models)
    n_files = len(files_to_summarize)
    n_models_used = min(num_models, n_files)

    file_paths_file = Path(output_dir) / "file_paths.txt"

    if file_paths_file.exists():
        with open(file_paths_file, "r") as f:
            all_file_paths = [line.strip() for line in f if line.strip()]
    else:
        all_file_paths = files_to_summarize

    file_paths_str = "\n".join(all_file_paths)

    static_message = f"""
<task>
Analyze the given file and generate a codebase overview in JSON format, following the provided codebase overview description and JSON schema and using additional context provided by user (if available).
</task>

<instructions>
1. The path of the file to be analyzed is provided in <file_path>...</file_path>.
2. The content of the file to analyzed is provided in <file_content>...</file_content>.
3. Use the paths as provided in `imported_files`.
4. The paths of all files in the codebase are provided in <all_file_paths_in_codebase>...</all_file_paths_in_codebase> below.
5. The output JSON should be wrapped in triple backticks (including the word `json`).
6. Don't output anything else other than the JSON wrapped within triple backticks.
</instructions>

<additional_context>
{additional_context}
</additional_context>

{prompts["codebase_overview_description"]}

{prompts["codebase_overview_schema"]}

<all_file_paths_in_codebase>
{file_paths_str}
</all_file_paths_in_codebase>

    """

    log.info(f"Processing {n_files} files using {n_models_used} model-region pairs")

    # Create a shared file queue and results dictionary
    # Check the size of each file and sort by size from large to small to speed up the process
    file_sizes = []
    for file_path in files_to_summarize:
        try:
            size = (Path(codebase_dir) / Path(file_path)).stat().st_size
            file_sizes.append((file_path, size))
        except OSError:
            file_sizes.append((file_path, 0))

    file_sizes.sort(key=lambda x: x[1], reverse=True)

    file_queue = [file_path for file_path, _ in file_sizes]

    # Create a thread-safe counter for tracking progress and retry tracking
    counter = {"completed": 0, "retry_counts": {}, "lock": threading.Lock()}

    # Process files in parallel using all available models
    results = {}
    with ThreadPoolExecutor(max_workers=n_models_used) as executor:
        futures = []

        # Submit one worker task per model
        for model_config in models:
            future = executor.submit(
                process_file_queue,
                file_queue,
                model_config,
                results,
                counter,
                codebase_dir,
                str(output_dir),
                static_message,
                prompts["system_message"],
            )
            futures.append(future)

        # Monitor progress
        monitor_progress(futures, counter, n_files)

    # Wait for all workers to complete and handle any exceptions
    for future in futures:
        future.result()

    log.info(f"Successfully processed {len(results)} files")
    return results
