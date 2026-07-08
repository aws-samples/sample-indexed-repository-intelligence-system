# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import logging
from strands import tool, ToolContext
from pathlib import Path

from .utils import (
    read_multiple_files,
    load_codebase_overview_context,
    build_user_message,
    identify_relevant_files,
)
from ..utils.utils import (
    load_default_config,
    construct_output_dir,
    get_additional_context,
)
from ..utils.bedrock import estimate_tokens
from ..summarize.utils import load_prompts

log = logging.getLogger(__name__)

# Load defaults at module import
_DEFAULT_CONFIG = load_default_config()
_DEFAULT_PROMPTS = load_prompts()

# Toggle context capping (set to False to disable for A/B comparison)
_ENABLE_CONTEXT_CAPPING = True

# Budget constants (in tokens) — defaults, overridden by config.yaml file_retrieval section
_ORCHESTRATOR_RESERVE = 30_000  # system prompt + conversation overhead + response room
_OVERVIEW_BUDGET_RATIO = 0.35  # max 35% of tool budget goes to overview


def _cap_overview(overview: dict, max_tokens: int) -> dict:
    """Progressively reduce overview to fit within token budget.

    Tiers:
      1. Full overview (as-is)
      2. purpose + imported_files only
      3. purpose only
      4. Truncate file count (drop least important files)
    """
    serialized = json.dumps(overview, separators=(",", ":"))
    current_tokens = estimate_tokens(serialized)

    if current_tokens <= max_tokens:
        log.debug(
            f"Overview cap tier 1 (full): {current_tokens}t <= {max_tokens}t budget"
        )
        return overview

    # Tier 2: purpose + imported_files
    tier2 = {}
    for fp, data in overview.items():
        entry = {}
        if isinstance(data, dict):
            if "purpose" in data:
                entry["purpose"] = data["purpose"]
            if "imported_files" in data:
                entry["imported_files"] = data["imported_files"]
        tier2[fp] = entry if entry else data

    serialized = json.dumps(tier2, separators=(",", ":"))
    current_tokens = estimate_tokens(serialized)
    if current_tokens <= max_tokens:
        log.debug(
            f"Overview cap tier 2 (purpose+imports): {current_tokens}t <= {max_tokens}t budget"
        )
        return tier2

    # Tier 3: purpose only
    tier3 = {}
    for fp, data in overview.items():
        if isinstance(data, dict) and "purpose" in data:
            tier3[fp] = {"purpose": data["purpose"]}
        else:
            tier3[fp] = data

    serialized = json.dumps(tier3, separators=(",", ":"))
    current_tokens = estimate_tokens(serialized)
    if current_tokens <= max_tokens:
        log.debug(
            f"Overview cap tier 3 (purpose only): {current_tokens}t <= {max_tokens}t budget"
        )
        return tier3

    # Tier 4: truncate file count
    files = list(tier3.items())
    while current_tokens > max_tokens and len(files) > 10:
        files = files[: len(files) * 3 // 4]  # drop 25% from the tail each iteration
        truncated = dict(files)
        serialized = json.dumps(truncated, separators=(",", ":"))
        current_tokens = estimate_tokens(serialized)

    log.debug(
        f"Overview cap tier 4 (truncated to {len(files)} files): {current_tokens}t"
    )
    return dict(files)


def _cap_file_content(file_content: str, max_tokens: int) -> str:
    """Truncate file content to fit within token budget.

    Splits by file boundaries (assumes files are separated by markers),
    and trims each file proportionally from the end if needed.
    """
    current_tokens = estimate_tokens(file_content)
    if current_tokens <= max_tokens:
        return file_content

    # Simple proportional truncation: keep ratio of allowed/current
    ratio = max_tokens / current_tokens
    max_chars = int(len(file_content) * ratio * 0.95)  # 5% safety margin
    truncated = file_content[:max_chars]
    log.debug(
        f"File content truncated from ~{current_tokens}t to ~{estimate_tokens(truncated)}t"
    )
    return truncated


@tool(context=True)
def file_retrieval_agent(query: str, tool_context: ToolContext) -> str:
    """
    Return contents helpful for answer questions.

    This tool performs a two-stage process:
    1. File Identification: Analyzes the codebase overview to identify files most relevant to the query
    2. File loading: Loads the identified files and generates comprehensive context

    The tool leverages codebase summaries, file relationships, and additional context to provide
    accurate and comprehensive context for answering questions about code structure, functionality, dependencies, implementation details, and more.

    Args:
        query: Natural language question or task about the codebase.

    Returns:
        String containing comprehensive context including the codebase overview and contents of relevant files

    Note:
        - Requires a pre-generated codebase overview (codebase_overview.json)
        - Uses configuration from config.yaml for model settings
        - Respects context window limits when reading files
    """
    config = _DEFAULT_CONFIG
    codebase_overview_path = Path(construct_output_dir()) / "codebase_overview.json"
    additional_context = get_additional_context()

    # Compute token budgets (read from config with fallback to module defaults)
    fr_config = config.get("file_retrieval", {})
    enable_capping = fr_config.get("enable_context_capping", _ENABLE_CONTEXT_CAPPING)
    orchestrator_reserve = fr_config.get(
        "orchestrator_reserve_tokens", _ORCHESTRATOR_RESERVE
    )
    overview_ratio = fr_config.get("overview_budget_ratio", _OVERVIEW_BUDGET_RATIO)

    context_window = config["context_window_size"]
    tool_budget = context_window - orchestrator_reserve
    overview_budget = int(tool_budget * overview_ratio)
    file_content_budget = tool_budget - overview_budget

    if enable_capping:
        log.debug(
            f"Token budgets: window={context_window}, tool={tool_budget}, overview={overview_budget}, files={file_content_budget}"
        )
    else:
        log.debug("Context capping disabled — returning full content")

    # Step 1: Identify relevant files
    identified_files = identify_relevant_files(
        query=query,
        config=config,
        codebase_overview_path=codebase_overview_path,
        additional_context=additional_context,
        system_message=_DEFAULT_PROMPTS["file_identifier_system_message"],
    )

    # Step 2: Read identified files
    file_context_dict = read_multiple_files(
        paths=identified_files,
        max_characters=config["context_window_size"] * 2,
        codebase_dir=tool_context.agent.state.get("codebase_dir")
        or config["codebase_dir"],
    )

    # Cap file content to budget (if enabled)
    if enable_capping:
        file_content = _cap_file_content(
            file_context_dict["file_content"], file_content_budget
        )
    else:
        file_content = file_context_dict["file_content"]

    # Step 3: Load and cap overview
    response_generator_overview = load_codebase_overview_context(
        path=codebase_overview_path,
        character_threshold=config["context_window_size"],
    )
    if enable_capping:
        response_generator_overview = _cap_overview(
            response_generator_overview, overview_budget
        )

    # Step 4: Build final message
    response_generator_message = build_user_message(
        query=query,
        codebase_overview=response_generator_overview,
        additional_context=additional_context,
        mode="respond",
        file_info=file_content,
        enable_cache_point=config.get("enable_prompt_caching", False),
    )

    if enable_capping:
        msg_tokens = estimate_tokens(response_generator_message)

        # Safety net: hard truncate if still over budget
        if msg_tokens > tool_budget:
            ratio = tool_budget / msg_tokens
            max_chars = int(len(response_generator_message) * ratio * 0.95)
            response_generator_message = response_generator_message[:max_chars]
            log.warning(
                f"Safety net: hard-truncated return message from ~{msg_tokens}t to fit {tool_budget}t budget"
            )
    return response_generator_message
