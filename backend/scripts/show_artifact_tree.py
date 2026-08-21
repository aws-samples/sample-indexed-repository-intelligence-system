# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#!/usr/bin/env python3
"""
Artifact Tree Visualization Script

Shows the project artifact tree that will be included for indexing, mirroring
show_project_tree.py for the codebase. Only files with supported artifact
extensions are shown; everything else is reported as filtered out.

Usage:
    python backend/scripts/show_artifact_tree.py [--artifacts PATH] [--codebase PATH]
"""

import sys
import argparse
from pathlib import Path

# Add the project root to Python path (parent of backend/)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from iris.artifacts import format_extension_list
    from iris.artifacts.artifact_file_management import validate_artifact_tree
except ImportError as e:
    print(f"❌ Error importing IRIS modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)


def show_tree(artifact_dir=None, codebase_dir=None):
    """
    Display the artifact tree that will be included for indexing.

    Args:
        artifact_dir: Path to the artifacts directory (optional)
        codebase_dir: Path to the codebase directory, used to locate the cache

    Returns:
        True on success, False on error. A missing/unconfigured artifact
        directory is treated as success (artifact indexing is optional).
    """
    try:
        print("📂 Artifact Tree Analysis")
        print("=" * 50)

        result = validate_artifact_tree(
            artifact_dir=artifact_dir, codebase_dir=codebase_dir
        )

        if result is None:
            print("⚠️  No usable artifact_dir configured (unset, placeholder, or")
            print("    missing directory). Skipping artifact indexing.")
            return True

        print(f"📂 Artifacts: {result.artifact_dir}")
        print()

        # Display change information
        if result.has_changed:
            change_details = result.change_details
            print("📝 Changes detected:")
            print(f"  • New artifacts: {len(change_details.get('new_files', []))}")
            print(
                f"  • Modified artifacts: {len(change_details.get('modified_files', []))}"
            )
            print(
                f"  • Deleted artifacts: {len(change_details.get('deleted_files', []))}"
            )
            print(f"  • Artifacts to process: {len(result.artifacts_to_process)}")
            print()

            for label, marker, key in (
                ("New", "+", "new_files"),
                ("Modified", "~", "modified_files"),
                ("Deleted", "-", "deleted_files"),
            ):
                entries = change_details.get(key) or []
                if not entries:
                    continue
                print(f"📄 {label} artifacts (showing first 5 of {len(entries)}):")
                for file_path in entries[:5]:
                    print(f"   {marker} {file_path}")
                if len(entries) > 5:
                    print(f"   ... and {len(entries) - 5} more")
                print()
        else:
            print("✅ No changes detected - artifact context is up to date")
            print()

        # Display the tree
        print(f"📁 Artifact tree ({result.total_artifacts} artifacts):")
        print("-" * 50)
        print(result.tree_display)
        print("-" * 50)

        # Report what was filtered out
        print()
        if result.filtered_out_files:
            print(
                f"🚫 Filtered out {len(result.filtered_out_files)} file(s) with "
                "unsupported extensions:"
            )
            for ext, count in result.filtered_out_extensions[:10]:
                print(f"   • {ext} ({count})")
            if len(result.filtered_out_extensions) > 10:
                print(
                    f"   ... and {len(result.filtered_out_extensions) - 10} more extensions"
                )
            print("   These files are not indexed as artifacts.")
        else:
            print("🚫 No files were filtered out - all files are supported artifacts.")

        # Summary
        print()
        print("📊 Summary:")
        print(f"  • Total artifacts: {result.total_artifacts}")
        print(f"  • Artifacts to process: {len(result.artifacts_to_process)}")
        print(f"  • Filtered out: {len(result.filtered_out_files)}")
        print(f"  • Changes detected: {'Yes' if result.has_changed else 'No'}")

        print()
        print("✅ Supported artifact extensions:")
        print(f"   {format_extension_list()}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Show the artifact tree that will be included for indexing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python backend/scripts/show_artifact_tree.py                     # Use artifact_dir from config
  python backend/scripts/show_artifact_tree.py --artifacts /path   # Use specific path

Only files with supported artifact extensions ({format_extension_list()})
are indexed. Any other file, including source files such as .py or .js, is
filtered out and reported separately.
        """,
    )

    parser.add_argument(
        "--artifacts",
        "-a",
        help="Path to artifacts directory (defaults to artifact_dir in config.yaml)",
    )
    parser.add_argument(
        "--codebase",
        "-c",
        help="Path to codebase directory (defaults to config.yaml setting)",
    )

    args = parser.parse_args()

    success = show_tree(artifact_dir=args.artifacts, codebase_dir=args.codebase)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
