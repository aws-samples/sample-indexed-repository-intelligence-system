# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import re
import yaml
from aws_cdk import (
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_cognito as cognito,
    aws_ecr_assets as assets,
    aws_s3 as s3,
    Duration,
    CfnOutput,
    RemovalPolicy,
)
import aws_cdk.aws_bedrock_agentcore_alpha as agentcore
from constructs import Construct
from cdk_nag import NagSuppressions


class IrisStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Load configuration
        self.config = self._load_config()

        # Validate auth method - only Cognito is supported
        # Auth method is hardcoded to cognito_auth

        # Create S3 bucket for server access logs (logs for the log buckets)
        # This bucket does NOT have server access logging enabled (to avoid infinite loop)
        self.server_access_logs_bucket = s3.Bucket(
            self,
            "ServerAccessLogsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            # No server_access_logs_bucket to avoid infinite recursion
        )

        # Cognito feeds the AgentCore Runtime JWT authorizer.
        user_pool, user_pool_client = self._create_cognito_user_pool()

        self._build_agentcore_mode(user_pool, user_pool_client)

    def _build_agentcore_mode(self, user_pool, user_pool_client):
        """Serverless deployment: AgentCore Runtime backend + S3/CloudFront static frontend.

        The browser invokes the Runtime data-plane endpoint directly (Cognito JWT
        auth), and the static React app is served from S3 via CloudFront.
        """
        agentcore_runtime = self._create_agentcore_runtime(user_pool, user_pool_client)
        distribution, site_bucket = self._create_static_frontend()

        self._create_agentcore_outputs(
            agentcore_runtime, distribution, site_bucket, user_pool, user_pool_client
        )

    def _suppress_nag(self, resource, suppressions):
        """Add CDK NAG suppressions to a resource"""
        NagSuppressions.add_resource_suppressions(resource, suppressions)

    def _load_config(self):
        """Load configuration from config.yaml with defaults"""
        try:
            with open("config.yaml", "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # Default config if file not found
            return {"auth": {"method": "cognito_auth"}}

    def _resolve_runtime_name(self):
        """Resolve the AgentCore Runtime name for this deployment.

        AgentCore Runtime names are unique per account+region and must match
        ``[a-zA-Z][a-zA-Z0-9_]{0,47}`` (letters, digits, underscores only — no
        hyphens). We read ``runtime_name`` from config.yaml (deploy.sh proposes
        one derived from the stack name, lets the user confirm/change it, and
        checks availability). If it is unset we fall back to sanitizing the
        stack name so distinct stacks don't collide on a single hardcoded name.
        The value is always sanitized so an out-of-spec config can't surface as
        a cryptic deploy-time error.
        """
        raw = self.config.get("runtime_name") or self.stack_name
        # Replace any disallowed character with an underscore, then ensure the
        # name starts with a letter and fits the 48-char limit.
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
        if not sanitized or not sanitized[0].isalpha():
            sanitized = f"iris_{sanitized}"
        return sanitized[:48]

    def _create_agentcore_execution_role(self):
        """Create the IAM execution role for the AgentCore Runtime.

        Trusts bedrock-agentcore.amazonaws.com and grants Bedrock invoke
        (+ optional guardrail + optional S3) permissions. CloudWatch Logs /
        X-Ray / ECR are added by the Runtime construct.
        """
        role = iam.Role(
            self,
            "AgentCoreExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        )

        bedrock_invoke_resources = [
            "arn:aws:bedrock:*::inference-profile/*",
            f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
            "arn:aws:bedrock:*::foundation-model/*",
        ]
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:Invoke*", "bedrock:Converse*"],
                resources=bedrock_invoke_resources,
            )
        )

        guardrail_id = self.config.get("guardrail_id", "")
        if guardrail_id:
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["bedrock:ApplyGuardrail"],
                    resources=[
                        f"arn:aws:bedrock:{self.region}:{self.account}:guardrail/{guardrail_id}"
                    ],
                )
            )

        # S3 read for codebase artifacts (S3 mode).
        s3_bucket = self.config.get("codebase_artifacts", {}).get("bucket", "")
        kms_key_arn = self.config.get("codebase_artifacts", {}).get("kms_key_arn", "")
        if s3_bucket:
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:ListBucket"],
                    resources=[
                        f"arn:aws:s3:::{s3_bucket}",
                        f"arn:aws:s3:::{s3_bucket}/*",
                    ],
                )
            )
            if kms_key_arn:
                role.add_to_policy(
                    iam.PolicyStatement(
                        actions=["kms:Decrypt", "kms:DescribeKey"],
                        resources=[kms_key_arn],
                    )
                )

        nag_suppressions = [
            {
                "id": "AwsSolutions-IAM5",
                "reason": "Bedrock system-defined inference profiles and foundation models have no account ID in their ARN; customer application profiles include the account. Wildcard on model/region is required to support any configured model.",
                "appliesTo": [
                    "Action::bedrock:Invoke*",
                    "Action::bedrock:Converse*",
                    "Resource::arn:aws:bedrock:*::inference-profile/*",
                    "Resource::arn:aws:bedrock:*:<AWS::AccountId>:inference-profile/*",
                    "Resource::arn:aws:bedrock:*::foundation-model/*",
                ],
            }
        ]
        if s3_bucket:
            nag_suppressions.append(
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "IRIS requires access to all objects in the specified S3 bucket for codebase artifacts",
                    "appliesTo": [f"Resource::arn:aws:s3:::{s3_bucket}/*"],
                }
            )
        # The AgentCore Runtime L2 construct adds a workload-identity permission to
        # the execution role (for AgentCore Identity / GetWorkloadAccessToken). The
        # directory/workload-identity name is generated at deploy time, so the
        # construct scopes it with a wildcard on the identity name — this is
        # construct-managed and required for the Runtime to obtain its workload token.
        nag_suppressions.append(
            {
                "id": "AwsSolutions-IAM5",
                "reason": "CloudWatch Logs, X-Ray, and AgentCore workload-identity permissions are added by the AgentCore Runtime L2 construct. Log group/stream and workload-identity names are generated at deploy time, and X-Ray PutTraceSegments/PutTelemetryRecords do not support resource-level scoping, so these wildcards are required and construct-managed.",
                "appliesTo": [
                    f"Resource::arn:aws:logs:{self.region}:<AWS::AccountId>:log-group:/aws/bedrock-agentcore/runtimes/*",
                    f"Resource::arn:aws:logs:{self.region}:<AWS::AccountId>:log-group:*",
                    f"Resource::arn:aws:logs:{self.region}:<AWS::AccountId>:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*",
                    "Resource::*",
                    f"Resource::arn:aws:bedrock-agentcore:{self.region}:<AWS::AccountId>:workload-identity-directory/default/workload-identity/*",
                ],
            }
        )
        self._suppress_nag(role.node.find_child("DefaultPolicy"), nag_suppressions)

        return role

    def _create_agentcore_runtime(self, user_pool, user_pool_client):
        """Create the AgentCore Runtime hosting the IRIS agent.

        The browser invokes the Runtime data-plane endpoint directly; the Runtime's
        Cognito JWT authorizer validates the user-pool tokens. Container is built
        from backend/Dockerfile.agentcore as an ARM64 image (Runtime requires ARM64).
        """
        execution_role = self._create_agentcore_execution_role()

        s3_bucket = self.config.get("codebase_artifacts", {}).get("bucket", "")
        s3_prefix = self.config.get("codebase_artifacts", {}).get("prefix", "")
        use_s3_mode = bool(s3_bucket)

        # Environment for the agent process inside the microVM. No CORS_ORIGINS:
        # the browser hits the AWS data-plane endpoint (which handles CORS), so the
        # app never sees cross-origin requests. No app-level auth env: the Runtime
        # authorizer validates JWTs before the request reaches the container.
        environment = {
            "AWS_DEFAULT_REGION": self.region,
        }
        if use_s3_mode:
            environment["S3_BUCKET"] = s3_bucket
            if s3_prefix:
                environment["S3_PREFIX"] = s3_prefix

        # Build the ARM64 container from the project root. In S3 mode the image
        # downloads the codebase + representation from S3 at boot; otherwise it
        # bakes them in at build time.
        # The exclude list, critically, drops
        # infra/cdk.out — without it the asset bundles its own output directory
        # recursively and fills the disk (ENOSPC).
        dockerfile = (
            "backend/Dockerfile.agentcore_s3"
            if use_s3_mode
            else "backend/Dockerfile.agentcore"
        )
        artifact = agentcore.AgentRuntimeArtifact.from_asset(
            "../",
            file=dockerfile,
            platform=assets.Platform.LINUX_ARM64,
            exclude=[
                "**/.venv",
                "**/venv",
                "**/__pycache__",
                "**/cdk.out",
                "infra/cdk.out",
                "**/.git",
                "**/node_modules",
                "**/*.pyc",
                "**/.DS_Store",
            ],
        )

        runtime = agentcore.Runtime(
            self,
            "IrisAgentRuntime",
            runtime_name=self._resolve_runtime_name(),
            agent_runtime_artifact=artifact,
            execution_role=execution_role,
            environment_variables=environment,
            protocol_configuration=agentcore.ProtocolType.HTTP,
            network_configuration=agentcore.RuntimeNetworkConfiguration.using_public_network(),
            authorizer_configuration=agentcore.RuntimeAuthorizerConfiguration.using_cognito(
                user_pool,
                [user_pool_client],
            ),
        )

        return runtime

    def _create_static_frontend(self):
        """Host the built React app in a private S3 bucket behind CloudFront (OAC).

        The frontend build + runtime-config.js injection + S3 upload is handled by
        deploy.sh (which knows the AgentRuntimeArn from the stack output). This method
        provisions the bucket, distribution, and SPA routing; it does not deploy
        assets itself so the ARN can be injected after the stack exists.
        """
        # Private bucket for the static site (no public access; served via OAC).
        site_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            server_access_logs_bucket=self.server_access_logs_bucket,
            server_access_logs_prefix="frontend-s3-access/",
        )

        cloudfront_logs_bucket = s3.Bucket(
            self,
            "FrontendCloudFrontLogsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
            server_access_logs_bucket=self.server_access_logs_bucket,
            server_access_logs_prefix="frontend-cloudfront-access/",
        )

        # S3 origin with Origin Access Control (OAC) — bucket stays private.
        s3_origin = origins.S3BucketOrigin.with_origin_access_control(site_bucket)

        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
                compress=True,
            ),
            default_root_object="index.html",
            # SPA routing: serve index.html for client-side routes (403/404 -> app).
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
            enable_ipv6=False,
            enable_logging=True,
            log_bucket=cloudfront_logs_bucket,
            log_file_prefix="frontend-cloudfront-access-logs/",
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            comment="IRIS - static frontend (AgentCore mode)",
        )

        self._suppress_nag(
            distribution,
            [
                {
                    "id": "AwsSolutions-CFR4",
                    "reason": "Default CloudFront certificate uses TLSv1 minimum - custom certificate requires domain ownership",
                },
                {
                    "id": "AwsSolutions-CFR1",
                    "reason": "Geo restriction is not required for this internal tool",
                },
                {
                    "id": "AwsSolutions-CFR2",
                    "reason": "WAF is out of scope for this proof-of-value; access is gated by Cognito auth at the Runtime layer",
                },
            ],
        )

        return distribution, site_bucket

    def _create_agentcore_outputs(
        self, agentcore_runtime, distribution, site_bucket, user_pool, user_pool_client
    ):
        """Stack outputs for AgentCore mode (consumed by deploy.sh for frontend config)."""
        CfnOutput(self, "CloudFrontURL", value=f"https://{distribution.domain_name}")
        CfnOutput(
            self,
            "AgentRuntimeArn",
            value=agentcore_runtime.agent_runtime_arn,
            description="ARN of the IRIS AgentCore Runtime (the frontend invokes this directly).",
        )
        CfnOutput(
            self,
            "FrontendBucketName",
            value=site_bucket.bucket_name,
            description="S3 bucket to sync the built React app into.",
        )
        CfnOutput(self, "AuthMethod", value="cognito_auth")
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(
            self, "CognitoUserPoolClientId", value=user_pool_client.user_pool_client_id
        )
        CfnOutput(
            self,
            "CognitoUserPoolUrl",
            value=f"https://{self.region}.console.aws.amazon.com/cognito/v2/idp/user-pools/{user_pool.user_pool_id}/user-management/users?region={self.region}",
        )

    def _create_cognito_user_pool(self):
        """Create Cognito User Pool and User Pool Client for authentication"""

        # Hardcoded auth configuration - users created via console
        allow_self_signup = False  # Always false - users created via console
        allowed_domains = [
            "amazon.com"
        ]  # Default domain (not enforced for console users)

        # Create Lambda function for pre-signup validation (only if self-signup is enabled)
        lambda_triggers = {}
        if allow_self_signup:
            pre_signup_lambda = _lambda.Function(
                self,
                "PreSignupLambda",
                runtime=_lambda.Runtime.PYTHON_3_13,
                handler="pre_signup_lambda.handler",
                code=_lambda.Code.from_asset("lambda/cognito_auth"),
                environment={"ALLOWED_DOMAINS": ",".join(allowed_domains)},
                timeout=Duration.seconds(30),
            )

            # Suppress NAG warning for AWS managed policy
            self._suppress_nag(
                pre_signup_lambda.role,
                [
                    {
                        "id": "AwsSolutions-IAM4",
                        "reason": "Lambda function uses standard AWS managed policy for basic execution permissions",
                        "appliesTo": [
                            "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                        ],
                    }
                ],
            )

            lambda_triggers = cognito.UserPoolTriggers(pre_sign_up=pre_signup_lambda)

        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="IrisUserPool",
            sign_in_aliases=cognito.SignInAliases(email=True, username=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            self_sign_up_enabled=allow_self_signup,  # Use config value
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True)
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            lambda_triggers=lambda_triggers if lambda_triggers else None,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Suppress NAG warning for disabled advanced security mode.
        # COG3 (advanced_security_mode) and COG8 (feature plan / Plus tier) flag the
        # same gap through the old and new Cognito APIs respectively. The pool is
        # intentionally left on ESSENTIALS, so both are acknowledged together.
        # NOTE: this accepts the risk rather than closing it — ESSENTIALS has no
        # threat protection (malicious sign-in detection, compromised-password
        # checks). Revisit with feature_plan=cognito.FeaturePlan.PLUS if this
        # deployment ever fronts untrusted users.
        self._suppress_nag(
            user_pool,
            [
                {
                    "id": "AwsSolutions-COG3",
                    "reason": "Advanced security mode disabled due to ESSENTIALS pricing tier limitation - threat protection features not supported",
                },
                {
                    "id": "AwsSolutions-COG8",
                    "reason": "Cognito feature plan intentionally left at ESSENTIALS; Plus tier threat protection is not required for this deployment (same rationale as AwsSolutions-COG3)",
                },
            ],
        )

        user_pool_client = cognito.UserPoolClient(
            self,
            "UserPoolClient",
            user_pool=user_pool,
            user_pool_client_name="IrisClient",
            auth_flows=cognito.AuthFlow(user_srp=True),
            generate_secret=False,  # Required for frontend applications
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO
            ],
        )

        return user_pool, user_pool_client
