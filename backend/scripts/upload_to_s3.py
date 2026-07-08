# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#!/usr/bin/env python3
"""
Upload local codebase zips to S3 following the same structure as generate_summary.py
"""

import sys
import boto3
from pathlib import Path


def upload_to_s3(file_path, bucket, key):
    """Upload file to S3."""
    s3 = boto3.client("s3")
    s3.upload_file(str(file_path), bucket, key)


def upload_codebase_to_s3(codebase_artifacts_dir, s3_bucket, s3_prefix=None):
    """Upload codebase zips to S3."""

    artifacts_path = Path(codebase_artifacts_dir)

    # Find zip files in the artifacts directory
    codebase_zip = None
    representation_zip = None

    for zip_file in artifacts_path.glob("codebase/*.zip"):
        codebase_zip = zip_file
        break

    for zip_file in artifacts_path.glob("codebase_representation/*_representation.zip"):
        representation_zip = zip_file
        break

    if not codebase_zip:
        print(f"❌ Codebase zip not found in: {artifacts_path}/codebase/")
        sys.exit(1)

    if not representation_zip:
        print(
            f"❌ Representation zip not found in: {artifacts_path}/codebase_representation/"
        )
        sys.exit(1)

    # Extract codebase name from zip filename
    codebase_name = codebase_zip.stem

    try:
        # Upload codebase zip
        codebase_s3_key = f"default/codebase/{codebase_name}.zip"
        if s3_prefix:
            codebase_s3_key = f"{s3_prefix}/default/codebase/{codebase_name}.zip"

        print(f"☁️ Uploading codebase to s3://{s3_bucket}/{codebase_s3_key}")
        upload_to_s3(codebase_zip, s3_bucket, codebase_s3_key)

        # Upload representation zip
        representation_s3_key = (
            f"default/codebase_representation/{codebase_name}_representation.zip"
        )
        if s3_prefix:
            representation_s3_key = f"{s3_prefix}/default/codebase_representation/{codebase_name}_representation.zip"

        print(f"☁️ Uploading representation to s3://{s3_bucket}/{representation_s3_key}")
        upload_to_s3(representation_zip, s3_bucket, representation_s3_key)

        print("✅ Upload complete")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upload codebase zips to S3")
    parser.add_argument(
        "--codebase-artifacts-dir",
        required=True,
        help="Path to codebase artifacts directory containing zip files",
    )
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket to upload to")
    parser.add_argument("--s3-prefix", help="S3 prefix for upload")

    args = parser.parse_args()

    upload_codebase_to_s3(
        codebase_artifacts_dir=args.codebase_artifacts_dir,
        s3_bucket=args.s3_bucket,
        s3_prefix=args.s3_prefix,
    )
