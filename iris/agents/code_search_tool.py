# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Code Search Tool - Fast cross-platform codebase search.

Provides fast, accurate keyword search across the codebase using Python's re module.
Works consistently across Windows, macOS, and Linux.
Much faster than LLM-based file scanning for finding specific patterns.
"""

import fnmatch
import logging
import re
import signal
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from strands import tool, ToolContext

from ..utils.utils import load_default_config, get_ignore_patterns

log = logging.getLogger(__name__)

_DEFAULT_CONFIG = load_default_config()

_REGEX_TIMEOUT_SECONDS = 5


@contextmanager
def _regex_timeout(seconds: int):
    """Raise TimeoutError if the body takes longer than `seconds` to complete.

    Uses SIGALRM, which is only available on Unix. On Windows this is a no-op.
    """
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise TimeoutError("Regex operation timed out")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _should_ignore_path(path: Path, ignore_patterns: list[str]) -> bool:
    """Check if a path should be ignored based on ignore patterns."""
    path_str = str(path)

    for ignore in ignore_patterns:
        clean = ignore.rstrip("/")

        # Directory pattern
        if ignore.endswith("/"):
            if clean in path_str or path_str.endswith(clean):
                return True
        # File glob pattern
        elif "*" in ignore:
            if fnmatch.fnmatch(path_str, f"*{ignore}") or fnmatch.fnmatch(
                path.name, ignore
            ):
                return True
        # Exact file match
        else:
            if clean in path_str or path.name == clean:
                return True

    return False


def _should_include_file(file_path: Path, file_pattern: Optional[str]) -> bool:
    """Check if a file should be included based on file pattern."""
    if file_pattern is None:
        return True
    return fnmatch.fnmatch(file_path.name, file_pattern)


def _search_files(
    pattern: str,
    codebase_dir: str,
    ignore_patterns: list[str],
    case_sensitive: bool,
    max_results: int,
    context_lines: int,
    file_pattern: Optional[str],
) -> list[str]:
    """Search files using Python's re module for cross-platform compatibility."""
    results = []

    try:
        # Guard against catastrophic backtracking (ReDoS).
        # These checks run BEFORE re.compile to prevent hangs during compilation.
        _MAX_PATTERN_LENGTH = 200
        if len(pattern) > _MAX_PATTERN_LENGTH:
            raise ValueError(
                f"Regex pattern too long ({len(pattern)} chars, max {_MAX_PATTERN_LENGTH})"
            )
        # Detect nested quantifiers — the primary cause of catastrophic backtracking
        if re.search(r"\([^)]*[+*][^)]*\)[+*?{]", pattern):
            raise ValueError(
                "Regex pattern contains nested quantifiers which can cause "
                "catastrophic backtracking. Simplify the pattern."
            )

        regex_flags = 0 if case_sensitive else re.IGNORECASE
        with _regex_timeout(_REGEX_TIMEOUT_SECONDS):
            compiled_pattern = re.compile(pattern, regex_flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")
    except TimeoutError:
        raise ValueError(
            f"Regex pattern timed out during compilation after {_REGEX_TIMEOUT_SECONDS}s. Simplify the pattern."
        )

    codebase_path = Path(codebase_dir)

    # Recursively search through all files
    for file_path in codebase_path.rglob("*"):
        # Skip directories
        if file_path.is_dir():
            continue

        # Check if file should be ignored
        if _should_ignore_path(file_path, ignore_patterns):
            continue

        # Check if file matches the file pattern filter
        if not _should_include_file(file_path, file_pattern):
            continue

        try:
            # Read file content
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            # Search for matches in this file
            file_matches = 0
            for line_num, line in enumerate(lines, 1):
                try:
                    with _regex_timeout(_REGEX_TIMEOUT_SECONDS):
                        matched = compiled_pattern.search(line)
                except TimeoutError:
                    log.warning(
                        f"Regex timed out on {file_path}:{line_num} — skipping file"
                    )
                    break
                if matched:
                    # Check if we've exceeded max results for this file
                    if max_results > 0:
                        if file_matches >= max_results:
                            break

                    # Get relative path for cleaner output
                    rel_path = file_path.relative_to(codebase_path)

                    # Add context lines if requested
                    if context_lines > 0:
                        start_line = max(0, line_num - context_lines - 1)
                        end_line = min(len(lines), line_num + context_lines)

                        # Add context before
                        for ctx_line_num in range(start_line, line_num - 1):
                            ctx_line = lines[ctx_line_num].rstrip("\n")
                            results.append(f"{rel_path}:{ctx_line_num + 1}:{ctx_line}")

                        # Add the matching line
                        results.append(f"{rel_path}:{line_num}:{line.rstrip(chr(10))}")

                        # Add context after
                        for ctx_line_num in range(line_num, end_line):
                            ctx_line = lines[ctx_line_num].rstrip("\n")
                            results.append(f"{rel_path}:{ctx_line_num + 1}:{ctx_line}")

                        # Add separator between matches
                        results.append("--")
                    else:
                        # Just add the matching line
                        results.append(f"{rel_path}:{line_num}:{line.rstrip(chr(10))}")

                    file_matches += 1

        except (IOError, OSError) as e:
            log.warning(f"Could not read file {file_path}: {e}")
            continue

    return results


@tool(context=True)
def code_search_tool(
    pattern: str,
    tool_context: ToolContext,
    case_sensitive: bool = False,
    max_results: int = 50,
    context_lines: int = 2,
    file_pattern: Optional[str] = None,
) -> str:
    """
    Search the codebase for a pattern using Python's re module.

    Fast, accurate keyword search that returns matching lines with file paths
    and line numbers. Works consistently across Windows, macOS, and Linux.
    Much faster than LLM-based scanning for finding specific code patterns,
    function names, variable references, or text strings.

    Args:
        pattern: Search pattern (supports regex). Examples:
            - "def my_function" - find function definitions
            - "import.*boto3" - find boto3 imports (regex)
            - "TODO|FIXME" - find TODO or FIXME comments
            - "class.*Agent" - find Agent class definitions
        case_sensitive: If True, search is case-sensitive. Default: False.
        max_results: Maximum matches per file. Default: 50. Set to 0 for unlimited.
        context_lines: Number of context lines before/after each match. Default: 2.
        file_pattern: Glob pattern to filter files. Examples:
            - "*.py" - only Python files
            - "*.js" - only JavaScript files
            - "test_*.py" - only test files

    Returns:
        Search results with file paths, line numbers, and matching content.
        Format: "filepath:line_number:content"

    Examples:
        - Find all usages of a function: pattern="calculate_score"
        - Find class definitions: pattern="^class ", file_pattern="*.py"
        - Find config references: pattern="config\\[", case_sensitive=True
    """
    config = _DEFAULT_CONFIG
    codebase_dir = (
        tool_context.agent.state.get("codebase_dir") or config["codebase_dir"]
    )

    if not Path(codebase_dir).exists():
        return f"Error: Codebase directory not found: {codebase_dir}"

    ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)

    try:
        results = _search_files(
            pattern=pattern,
            codebase_dir=codebase_dir,
            ignore_patterns=ignore_patterns,
            case_sensitive=case_sensitive,
            max_results=max_results,
            context_lines=context_lines,
            file_pattern=file_pattern,
        )

        if not results:
            return f"No matches found for pattern: {pattern}"

        # Count matches (exclude separator lines)
        match_count = len(
            [line for line in results if line and not line.startswith("--")]
        )

        output = "\n".join(results)
        return f"Found {match_count} matches for '{pattern}':\n\n{output}"

    except ValueError as e:
        log.error(f"Invalid pattern: {e}")
        return f"Error: {e}"
    except Exception as e:
        log.error(f"Search failed: {e}", exc_info=True)
        return f"Error during search: {e}"
