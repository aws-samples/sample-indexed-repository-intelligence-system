# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#!/usr/bin/env python3
import os
import sys
import yaml
import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks
from stack import IrisStack

app = cdk.App()

# Load config
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Get region from context or environment
region = (
    app.node.try_get_context("region")
    or os.environ.get("AWS_DEFAULT_REGION")
    or os.environ.get("AWS_REGION")
)

if not region:
    print("Error: AWS region not specified.")
    print("Please set the region using one of these methods:")
    print("  1. Set AWS_DEFAULT_REGION environment variable")
    print("  2. Configure AWS CLI: aws configure")
    print("  3. Use CDK context: cdk synth --context region=us-east-1")
    sys.exit(1)

stack = IrisStack(
    app,
    config["app_name"],
    description="IRIS stack that lets you chat with GenAIIC delivered codebase for: understanding, troubleshooting, onboarding new engineers etc.",
    env=cdk.Environment(region=region),
)

# Add cdk_nag checks
cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

app.synth()
