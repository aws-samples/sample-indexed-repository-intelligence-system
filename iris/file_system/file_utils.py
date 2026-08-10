# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List
import logging
import chardet
import pathspec
from ..utils.utils import load_default_config

CONFIG = load_default_config()
MAX_FILE_SIZE = CONFIG["max_file_size"]
MAX_NOTEBOOK_SIZE = CONFIG["max_notebook_size"]
MAX_TOKENS = CONFIG["context_window_size"]

log = logging.getLogger(__name__)


def _atomic_json_write(filepath: Path, data, **json_kwargs) -> None:
    """Write JSON data atomically: write to a temp file then rename.

    This prevents data corruption if the process crashes mid-write.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(filepath.parent), suffix=".tmp", prefix=filepath.stem
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, **json_kwargs)
        os.replace(tmp_path, str(filepath))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def hash_file_content(file_path: Path) -> str:
    """
    Generate SHA256 hash of file content.

    Args:
        file_path: Path to file

    Returns:
        Hex string of SHA256 hash
    """
    try:
        with open(file_path, "rb") as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()
    except (OSError, IOError):
        # If we can't read the file, return a special hash
        return "unreadable"


def load_file_hashes(output_dir: str | Path) -> Dict[str, str]:
    """Load existing file hashes from disk."""
    hashes_file = Path(output_dir) / "file_hashes.json"
    if not hashes_file.exists():
        return {}

    try:
        with open(hashes_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # Fail soft so indexing can rebuild, but never silently: an unreadable
        # cache is indistinguishable from a first run to every caller.
        log.warning(
            f"Could not read {hashes_file} ({type(e).__name__}: {e}); "
            "treating file hashes as empty. Affected files will be re-summarized."
        )
        return {}


def load_codebase_overview(output_dir: str | Path) -> Dict[str, dict]:
    """Load existing codebase overview from disk."""
    overview_file = Path(output_dir) / "codebase_overview.json"
    if not overview_file.exists():
        return {}

    try:
        with open(overview_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # Fail soft so indexing can rebuild, but never silently: returning {}
        # here discards every cached summary, which is an expensive event to hide.
        log.warning(
            f"Could not read {overview_file} ({type(e).__name__}: {e}); "
            "treating the codebase overview as empty. The codebase will be re-indexed."
        )
        return {}


def save_codebase_overview(
    overview: dict,
    output_dir: str | Path,
):
    """Save codebase overview to disk (atomic write)."""
    overview_file = Path(output_dir) / "codebase_overview.json"
    _atomic_json_write(overview_file, overview, indent=2)


def load_codebase_metadata(output_dir: str | Path) -> Dict[str, any]:
    """Load codebase metadata from disk."""
    metadata_file = Path(output_dir) / "codebase_metadata.json"
    if not metadata_file.exists():
        return {}

    try:
        with open(metadata_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_codebase_metadata(metadata: dict, output_dir: str | Path):
    """Save codebase metadata to disk (atomic write)."""
    output_path = Path(output_dir)
    metadata_file = output_path / "codebase_metadata.json"
    _atomic_json_write(metadata_file, metadata, indent=2)


def update_codebase_metadata(output_dir: str | Path, metadata: dict):
    """
    Update codebase-level metadata.

    Metadata is stored in codebase_metadata.json.

    Args:
        output_dir: Output directory for metadata file
        metadata: Dict of metadata to update (e.g., {'evaluation_timestamp': '...'})
    """
    existing_metadata = load_codebase_metadata(output_dir)
    existing_metadata.update(metadata)
    save_codebase_metadata(existing_metadata, output_dir)
    log.info(f"Updated codebase metadata: {metadata}")


def get_codebase_metadata(output_dir: str | Path) -> dict:
    """
    Get codebase-level metadata.

    Returns:
        Dict of codebase metadata, or empty dict if not found
    """
    return load_codebase_metadata(output_dir)


def load_conversation_history(output_dir):
    """Load conversation history from file"""
    conversation_history_path = Path(output_dir) / "conversation_history.json"

    if conversation_history_path.exists():
        try:
            with open(conversation_history_path, "r") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Error loading conversation history: {str(e)}")
            # Reset the conversation history file
            with open(conversation_history_path, "w") as f:
                f.write("[]")

    return []


def save_conversation_history(conversation_history: list[dict], output_dir):
    """Save conversation history to file (atomic write)."""
    conversation_history_path = Path(output_dir) / "conversation_history.json"
    try:
        _atomic_json_write(conversation_history_path, conversation_history, indent=4)
    except Exception as e:
        log.warning(f"Error saving conversation history: {str(e)}")


def save_file_hashes(file_hashes: Dict[str, str], output_dir: str | Path):
    """Save file hashes to disk (atomic write)."""
    output_path = Path(output_dir)
    hashes_file = output_path / "file_hashes.json"
    _atomic_json_write(hashes_file, file_hashes, indent=2)


def generate_tree_structure(
    codebase_dir: str | Path, ignore_patterns: List[str]
) -> dict:
    """
    Generate structured tree representation of codebase for interactive display.

    Args:
        codebase_dir: Path to codebase directory
        ignore_patterns: List of gitignore-style patterns to ignore

    Returns:
        Dict representing directory tree structure

    Raises:
        FileNotFoundError: If codebase directory doesn't exist
        NotADirectoryError: If codebase_dir is not a directory
    """
    root_dir = Path(codebase_dir).resolve()

    if not root_dir.exists():
        raise FileNotFoundError(f"Directory '{root_dir}' does not exist")

    if not root_dir.is_dir():
        raise NotADirectoryError(f"'{root_dir}' is not a directory")

    # Create pathspec for gitignore-style matching
    ignore_spec = pathspec.PathSpec.from_lines("gitignore", ignore_patterns)

    def build_structure_recursive(current_path: Path) -> dict:
        """Recursively build tree structure."""
        try:
            # Sort: directories first, then files
            items = sorted(
                current_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())
            )
        except PermissionError:
            return {
                "name": current_path.name,
                "type": "directory",
                "error": "Permission denied",
                "children": [],
            }

        filtered_items = [
            item
            for item in items
            if not _should_ignore_item(item, root_dir, ignore_spec)
        ]

        children = []
        for item in filtered_items:
            if item.is_dir():
                children.append(build_structure_recursive(item))
            else:
                children.append(
                    {
                        "name": item.name,
                        "type": "file",
                        "size": item.stat().st_size if item.exists() else 0,
                    }
                )

        return {"name": current_path.name, "type": "directory", "children": children}

    return build_structure_recursive(root_dir)


def generate_tree_display(codebase_dir: str | Path, ignore_patterns: List[str]) -> str:
    """
    Generate visual tree representation of codebase structure.

    Args:
        codebase_dir: Path to codebase directory
        ignore_patterns: List of gitignore-style patterns to ignore

    Returns:
        String representation of directory tree

    Raises:
        FileNotFoundError: If codebase directory doesn't exist
        NotADirectoryError: If codebase_dir is not a directory
    """
    root_dir = Path(codebase_dir).resolve()

    if not root_dir.exists():
        raise FileNotFoundError(f"Directory '{root_dir}' does not exist")

    if not root_dir.is_dir():
        raise NotADirectoryError(f"'{root_dir}' is not a directory")

    # Create pathspec for gitignore-style matching
    ignore_spec = pathspec.PathSpec.from_lines("gitignore", ignore_patterns)

    tree_lines = [f"{root_dir.name}/"]

    def build_tree_recursive(current_path: Path, prefix: str = ""):
        """Recursively build tree display."""
        try:
            # Sort: directories first, then files
            items = sorted(
                current_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())
            )
        except PermissionError:
            tree_lines.append(f"{prefix}├── [Permission denied]")
            return

        filtered_items = [
            item
            for item in items
            if not _should_ignore_item(item, root_dir, ignore_spec)
        ]

        for i, item in enumerate(filtered_items):
            is_last = i == len(filtered_items) - 1
            current_prefix = "└── " if is_last else "├── "
            next_prefix = "    " if is_last else "│   "

            tree_lines.append(f"{prefix}{current_prefix}{item.name}")

            if item.is_dir():
                build_tree_recursive(item, prefix + next_prefix)

    build_tree_recursive(root_dir)
    return "\n".join(tree_lines)


def generate_hashes(codebase_dir: str | Path, file_paths: List[str]) -> Dict[str, str]:
    """
    Generate hashes for given file paths.

    Args:
        codebase_dir: Root directory of codebase
        file_paths: List of relative file paths

    Returns:
        Dict mapping file path to hash
    """
    codebase_path = Path(codebase_dir)
    file_hashes = {}

    for file_path in file_paths:
        full_path = codebase_path / file_path
        if full_path.exists() and full_path.is_file():
            file_hashes[file_path] = hash_file_content(full_path)

    return file_hashes


def _should_ignore_item(item: Path, root_dir: Path, ignore_spec) -> bool:
    """Helper to check if item should be ignored."""
    try:
        # Ignore files that will not be summarized due to size limit
        if item.is_file() and (
            (item.suffix != ".ipynb" and item.stat().st_size > MAX_FILE_SIZE)
            or item.stat().st_size > MAX_NOTEBOOK_SIZE
        ):
            return True

        rel_path = item.relative_to(root_dir)
        path_to_check = str(rel_path) + "/" if item.is_dir() else str(rel_path)
        return ignore_spec.match_file(path_to_check)
    except ValueError:
        return True


def collect_files(codebase_dir: str | Path, ignore_patterns: List[str]) -> List[str]:
    """
    Collect all allowed files from codebase, respecting ignore patterns.

    Args:
        codebase_dir: Path to codebase directory
        ignore_patterns: List of gitignore-style patterns to ignore

    Returns:
        List of relative file paths

    Raises:
        FileNotFoundError: If codebase directory doesn't exist
        NotADirectoryError: If codebase_dir is not a directory
    """
    root_dir = Path(codebase_dir).resolve()

    if not root_dir.exists():
        raise FileNotFoundError(f"Directory '{root_dir}' does not exist")

    if not root_dir.is_dir():
        raise NotADirectoryError(f"'{root_dir}' is not a directory")

    # Create pathspec for gitignore-style matching
    ignore_spec = pathspec.PathSpec.from_lines("gitignore", ignore_patterns)

    file_paths = []

    def collect_files_recursive(current_path: Path):
        """Recursively collect files."""
        try:
            items = current_path.iterdir()
        except PermissionError:
            return

        for item in items:
            if _should_ignore_item(item, root_dir, ignore_spec):
                continue

            if item.is_file():
                rel_path = item.relative_to(root_dir)
                file_paths.append(str(rel_path))
            elif item.is_dir():
                collect_files_recursive(item)

    collect_files_recursive(root_dir)
    return sorted(file_paths)


def to_absolute_path(path: str | Path, codebase_dir: str):
    """Convert a relative path to an absolute path using the codebase root directory."""
    path_obj = Path(path)
    if path_obj.is_absolute():
        return path_obj
    return Path(codebase_dir) / path


def remove_images_from_notebook(notebook: dict) -> None:
    try:
        for cell in notebook["cells"]:
            if "outputs" in cell:
                for output in cell["outputs"]:
                    if "data" in output:
                        if "image/png" in output["data"]:
                            output["data"]["image/png"] = ""
                        if "image/jpeg" in output["data"]:
                            output["data"]["image/jpeg"] = ""
    except Exception as e:
        log.warning(
            f"Error when removing images from notebook: {type(e).__name__}: {e}"
        )
        log.warning("Proceeding without image removal")


def handle_notebook(
    path: Path, max_notebook_size: int, return_too_large_message: bool = False
) -> tuple[str, int]:
    # Don't try to process if notebook is >2GB
    if path.stat().st_size > max_notebook_size:
        if return_too_large_message:
            return "File is too large to read", path.stat().st_size
        else:
            return "", path.stat().st_size

    notebook_json = json.loads(path.read_bytes())
    remove_images_from_notebook(notebook_json)
    notebook_str = json.dumps(notebook_json)

    return notebook_str, len(notebook_str)


def read_source(
    path: Path,
    codebase_dir: str,
    max_file_size: int = MAX_FILE_SIZE,
    max_notebook_size: int = MAX_NOTEBOOK_SIZE,
    max_tokens: int = MAX_TOKENS,
) -> str | None:
    # Convert to absolute path if needed
    if not path.is_absolute():
        path = to_absolute_path(path, codebase_dir)

    # Path containment check: ensure resolved path is within codebase root
    # Prevents path traversal attacks (e.g., ../../etc/passwd)
    resolved_path = path.resolve()
    resolved_root = Path(codebase_dir).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        log.warning(
            f"Path traversal blocked: {path} resolves outside codebase root {resolved_root}"
        )
        return None

    # Check if file exists
    if not path.exists():
        log.warning(f"Skipping file {path} - file does not exist")
        return None

    # Special handling for notebooks
    if path.suffix == ".ipynb":
        text, size = handle_notebook(path, max_notebook_size)
        if size > max_file_size:
            log.warning(
                f"Skipping notebook {path} - size {size} exceeds max_file_size {max_file_size}"
            )
            return None
    else:
        # 1. Skip obviously binary or huge files
        if path.stat().st_size > max_file_size:  # 2 MB
            log.warning(
                f"Skipping file {path} - size {path.stat().st_size} exceeds max_file_size {max_file_size}"
            )
            return None

        raw = path.read_bytes()

        # 2. Decode safely
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            enc = chardet.detect(raw)["encoding"] or "latin-1"
            text = raw.decode(enc, errors="replace")
            log.warning(f"File {path} had encoding issues, decoded with {enc}")

    # 3. Optional: truncate or chunk
    if len(text) > max_tokens:
        log.warning(f"Skipping large file {path}")
        ##TODO: chunk large files
        return None
    else:
        return text
