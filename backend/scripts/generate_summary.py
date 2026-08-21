# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#!/usr/bin/env python3
"""
Minimal script to generate codebase summary without agentic chat.
"""

import sys
import zipfile
import boto3
from pathlib import Path
from iris.artifacts import resolve_artifact_dir
from iris.generate_context import generate_context
from iris.generate_artifact_context import generate_artifact_context
from iris.utils.utils import (
    construct_output_dir,
    get_additional_context,
    get_ignore_patterns,
    load_default_config,
)

# Add the project root to Python path (parent of backend/)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def zip_directory(source_dir, zip_path, ignore_patterns=None):
    """Create a zip file from directory contents, respecting ignore patterns."""
    import pathspec

    ignore_spec = None
    if ignore_patterns:
        ignore_spec = pathspec.PathSpec.from_lines("gitignore", ignore_patterns)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        source_path = Path(source_dir)
        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(source_path)

                # Check if file should be ignored
                if ignore_spec and ignore_spec.match_file(str(rel_path)):
                    continue

                zipf.write(file_path, rel_path)


def upload_to_s3(file_path, bucket, key):
    """Upload file to S3."""
    s3 = boto3.client("s3")
    s3.upload_file(str(file_path), bucket, key)


def generate_codebase_summary(
    s3_bucket=None, s3_prefix=None, verbose=True, local_mode=False
):
    """Generate codebase summary and upload to S3 or save locally."""

    # Load config
    config = load_default_config()
    codebase_dir = config["codebase_dir"]
    context_file = config.get("context_file")

    # Set up paths and patterns
    output_dir = construct_output_dir(codebase_dir=codebase_dir)
    ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)
    additional_context = get_additional_context(filepath=context_file)

    try:
        # Generate context/summary
        result = generate_context(
            codebase_dir=codebase_dir,
            output_dir=str(output_dir),
            ignore_patterns=ignore_patterns,
            additional_context=additional_context,
            verbose=verbose,
        )

        if result.status == "error":
            print(f"❌ Error: {result.message}")
            sys.exit(1)
        else:
            print(f"✅ {result.message}")
            if verbose:
                print(f"📁 Output directory: {output_dir}")

        # Generate artifact context if a usable artifact_dir is configured.
        # resolve_artifact_dir() returns None for unset, blank, placeholder,
        # or non-existent directories.
        artifact_dir = resolve_artifact_dir(config)
        if artifact_dir:
            print("📄 Indexing project artifacts...")
            artifact_result = generate_artifact_context(
                artifact_dir=artifact_dir,
                output_dir=str(output_dir),
                config=config,
                verbose=verbose,
            )
            if artifact_result.status == "error":
                print(f"⚠️  Artifact indexing failed: {artifact_result.message}")
                print("   Continuing with codebase-only deployment...")
            else:
                print(f"✅ Artifacts: {artifact_result.message}")
        elif verbose:
            print("ℹ️  No usable artifact_dir configured — skipping artifact indexing")

        codebase_name = Path(codebase_dir).name

        if local_mode:
            # Find project root by looking for pyproject.toml or README.md
            current_path = Path(__file__).resolve()
            project_root = None

            # Walk up the directory tree to find project root
            for parent in current_path.parents:
                if (parent / "pyproject.toml").exists() or (
                    parent / "README.md"
                ).exists():
                    project_root = parent
                    break

            if not project_root:
                # Fallback: assume we're in backend/scripts and go up 2 levels
                project_root = Path(__file__).parent.parent.parent

            # Create directories
            codebase_dir_local = project_root / "codebase_artifacts" / "codebase"
            representation_dir = (
                project_root / "codebase_artifacts" / "codebase_representation"
            )
            codebase_dir_local.mkdir(parents=True, exist_ok=True)
            representation_dir.mkdir(parents=True, exist_ok=True)

            # Create codebase zip
            codebase_zip_path = codebase_dir_local / f"{codebase_name}.zip"
            print(f"📦 Creating codebase zip: {codebase_zip_path}")
            zip_directory(codebase_dir, codebase_zip_path, ignore_patterns)

            # Create representation zip
            representation_zip_path = (
                representation_dir / f"{codebase_name}_representation.zip"
            )
            print(f"📦 Creating representation zip: {representation_zip_path}")
            zip_directory(output_dir, representation_zip_path)

            print(f"✅ Zips saved to: {project_root / 'codebase_artifacts'}")
        else:
            # S3 upload mode
            codebase_zip_filename = f"{codebase_name}.zip"
            codebase_zip_path = Path(output_dir).parent / codebase_zip_filename

            print(f"📦 Creating codebase zip: {codebase_zip_path}")
            zip_directory(codebase_dir, codebase_zip_path, ignore_patterns)

            codebase_s3_key = (
                f"default/codebase/{codebase_zip_filename}"
                if not s3_prefix
                else f"{s3_prefix}/default/codebase/{codebase_zip_filename}"
            )
            print(f"☁️ Uploading codebase to s3://{s3_bucket}/{codebase_s3_key}")
            upload_to_s3(codebase_zip_path, s3_bucket, codebase_s3_key)
            codebase_zip_path.unlink()

            # Create and upload representation zip
            representation_zip_filename = f"{codebase_name}_representation.zip"
            representation_zip_path = (
                Path(output_dir).parent / representation_zip_filename
            )

            print(f"📦 Creating representation zip: {representation_zip_path}")
            zip_directory(output_dir, representation_zip_path)

            representation_s3_key = (
                f"default/codebase_representation/{representation_zip_filename}"
                if not s3_prefix
                else f"{s3_prefix}/default/codebase_representation/{representation_zip_filename}"
            )
            print(
                f"☁️ Uploading representation to s3://{s3_bucket}/{representation_s3_key}"
            )
            upload_to_s3(representation_zip_path, s3_bucket, representation_s3_key)
            representation_zip_path.unlink()

            print("✅ Upload complete")

        return result

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate codebase summary")
    parser.add_argument("--s3-bucket", help="S3 bucket to upload results")
    parser.add_argument("--s3-prefix", help="S3 prefix for upload")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Save zips locally in project root codebase_artifacts/ directory",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )

    args = parser.parse_args()

    if not args.local and not args.s3_bucket:
        parser.error("Either --local or --s3-bucket is required")

    generate_codebase_summary(
        s3_bucket=args.s3_bucket,
        s3_prefix=args.s3_prefix,
        verbose=not args.quiet,
        local_mode=args.local,
    )
