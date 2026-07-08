# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#!/usr/bin/env python3
"""
Project Tree Visualization Script

This script shows the project tree that will be included for summarization,
similar to the tree validation in iris/cli.py.

Usage:
    python backend/scripts/show_project_tree.py [--codebase PATH]
"""

import sys
import argparse
from pathlib import Path

# Add the project root to Python path (parent of backend/)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from iris.file_system.file_management import validate_tree
    from iris.utils.utils import load_default_config
except ImportError as e:
    print(f"❌ Error importing IRIS modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)


def show_tree(codebase_dir=None):
    """
    Display the project tree that will be included for summarization.

    Args:
        codebase_dir: Path to codebase directory (optional)
    """
    try:
        # Load configuration
        config = load_default_config()

        # Use provided codebase_dir or fall back to config, then to current directory
        if codebase_dir is None:
            codebase_dir = config.get("codebase_dir", ".")
            # If config has placeholder path, use current directory
            if codebase_dir == "/path/to/your/codebase":
                codebase_dir = "."

        print("🌳 Project Tree Analysis")
        print("=" * 50)
        print(f"📂 Codebase: {Path(codebase_dir).resolve()}")
        print()

        # Validate tree and get file information
        files_result = validate_tree(codebase_dir=codebase_dir)

        # Display change information
        if files_result.has_changed:
            change_details = files_result.change_details
            print("📝 Changes detected:")
            print(f"  • New files: {len(change_details.get('new_files', []))}")
            print(
                f"  • Modified files: {len(change_details.get('modified_files', []))}"
            )
            print(f"  • Deleted files: {len(change_details.get('deleted_files', []))}")
            print(f"  • Files to process: {len(files_result.files_to_process)}")
            print()

            # Show some examples of changes
            if change_details.get("new_files"):
                print(
                    f"📄 New files (showing first 5 of {len(change_details['new_files'])}):"
                )
                for file_path in change_details["new_files"][:5]:
                    print(f"   + {file_path}")
                if len(change_details["new_files"]) > 5:
                    print(f"   ... and {len(change_details['new_files']) - 5} more")
                print()

            if change_details.get("modified_files"):
                print(
                    f"📝 Modified files (showing first 5 of {len(change_details['modified_files'])}):"
                )
                for file_path in change_details["modified_files"][:5]:
                    print(f"   ~ {file_path}")
                if len(change_details["modified_files"]) > 5:
                    print(
                        f"   ... and {len(change_details['modified_files']) - 5} more"
                    )
                print()

            if change_details.get("deleted_files"):
                print(
                    f"🗑️  Deleted files (showing first 5 of {len(change_details['deleted_files'])}):"
                )
                for file_path in change_details["deleted_files"][:5]:
                    print(f"   - {file_path}")
                if len(change_details["deleted_files"]) > 5:
                    print(f"   ... and {len(change_details['deleted_files']) - 5} more")
                print()
        else:
            print("✅ No changes detected - codebase context is up to date")
            print()

        # Display the tree
        print(f"📁 File tree ({files_result.total_files} files):")
        print("-" * 50)
        print(files_result.tree_display)
        print("-" * 50)

        # Summary
        print()
        print("📊 Summary:")
        print(f"  • Total files: {files_result.total_files}")
        print(f"  • Files to process: {len(files_result.files_to_process)}")
        print(f"  • Changes detected: {'Yes' if files_result.has_changed else 'No'}")

        # Show ignore patterns being used
        print()
        print("🚫 Ignore patterns from config:")
        try:
            from iris.utils.utils import get_ignore_patterns

            ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)
            for pattern in ignore_patterns[:10]:  # Show first 10
                print(f"   • {pattern}")
            if len(ignore_patterns) > 10:
                print(f"   ... and {len(ignore_patterns) - 10} more patterns")
        except Exception:
            print("   • Could not load ignore patterns")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Show project tree that will be included for summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backend/scripts/show_project_tree.py                    # Use default codebase from config
  python backend/scripts/show_project_tree.py --codebase .       # Use current directory
  python backend/scripts/show_project_tree.py --codebase /path   # Use specific path

This script uses the same tree validation logic as the CLI tool to show exactly
which files will be included when generating codebase summaries.
        """,
    )

    parser.add_argument(
        "--codebase",
        "-c",
        help="Path to codebase directory (defaults to config.yaml setting or current directory)",
    )

    args = parser.parse_args()

    success = show_tree(codebase_dir=args.codebase)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
