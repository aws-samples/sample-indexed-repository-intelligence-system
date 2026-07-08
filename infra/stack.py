# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import yaml
import boto3
from aws_cdk import (
    Stack,
    Fn,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_logs as logs,
    aws_lambda as _lambda,
    aws_cognito as cognito,
    aws_ecr_assets as assets,
    aws_s3 as s3,
    Duration,
    CfnOutput,
    RemovalPolicy,
)
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

        # Create infrastructure components
        vpc = self._create_vpc()
        cluster = self._create_cluster(vpc)
        task_role = self._create_task_role()

        # Create Cognito authentication resources
        user_pool, user_pool_client = self._create_cognito_user_pool()

        # Create task definition with Cognito configuration
        task_definition = self._create_task_definition(
            task_role, user_pool, user_pool_client
        )
        service = self._create_service(cluster, task_definition)

        # Create CloudFront distribution with default SSL certificate
        distribution = self._create_cloudfront(service)

        # N1 fix: Wire CloudFront URL into backend CORS_ORIGINS so WebSocket
        # Origin checks pass in cloud deployments.
        cfn_task_def = task_definition.node.default_child
        cfn_task_def.add_property_override(
            "ContainerDefinitions.1.Environment.0.Value",
            Fn.join(
                ",",
                [
                    Fn.join("", ["https://", distribution.domain_name]),
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ],
            ),
        )

        self._create_outputs(distribution, service, user_pool, user_pool_client)

    def _suppress_nag(self, resource, suppressions):
        """Add CDK NAG suppressions to a resource"""
        NagSuppressions.add_resource_suppressions(resource, suppressions)

    def _get_cloudfront_prefix_list(self):
        """Get CloudFront managed prefix list ID for the current region"""
        try:
            ec2_client = boto3.client("ec2", region_name=self.region)
            response = ec2_client.describe_managed_prefix_lists(
                Filters=[
                    {
                        "Name": "prefix-list-name",
                        "Values": ["com.amazonaws.global.cloudfront.origin-facing"],
                    }
                ]
            )
            if response["PrefixLists"]:
                return response["PrefixLists"][0]["PrefixListId"]
            else:
                raise ValueError(
                    f"CloudFront prefix list not found in region {self.region}"
                )
        except Exception as e:
            raise ValueError(f"Failed to get CloudFront prefix list: {str(e)}")

    def _load_config(self):
        """Load configuration from config.yaml with defaults"""
        try:
            with open("config.yaml", "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # Default config if file not found
            return {
                "resources": {
                    "total_memory_mib": 4096,
                    "total_cpu": 2048,
                    "frontend": {"memory_percentage": 40, "cpu_percentage": 40},
                    "backend": {"memory_percentage": 60, "cpu_percentage": 60},
                },
                "service": {"desired_count": 1, "max_azs": 2},
                "auth": {"method": "cognito_auth"},
                "logging": {"retention_days": 7},
            }

    def _create_vpc(self):
        """Create Amazon VPC with 2 AZs for high availability and VPC endpoints"""
        vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=self.config["service"]["max_azs"],
            nat_gateways=1,  # Required for Cognito JWKS endpoint (no VPC endpoint available)
            flow_logs={
                "default": ec2.FlowLogOptions(
                    destination=ec2.FlowLogDestination.to_cloud_watch_logs()
                )
            },
        )

        # Add VPC Endpoints for AWS services (reduces NAT Gateway usage)

        # S3 Gateway Endpoint (free) - for customer codebase artifacts
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # Amazon Bedrock Runtime Interface Endpoint - for AI API calls
        vpc.add_interface_endpoint(
            "BedrockRuntimeEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
            private_dns_enabled=True,
        )

        # CloudWatch Logs Interface Endpoint - for application logging
        vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            private_dns_enabled=True,
        )

        # ECR API Endpoint - for pulling container images
        vpc.add_interface_endpoint(
            "EcrApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
            private_dns_enabled=True,
        )

        # ECR Docker Endpoint - for pulling container layers
        vpc.add_interface_endpoint(
            "EcrDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            private_dns_enabled=True,
        )

        # Note: Cognito does not have VPC endpoints
        # Backend fetches JWKS from cognito-idp.<region>.amazonaws.com
        # This requires NAT Gateway for internet access to Cognito's public endpoint
        # VPC endpoints above reduce NAT Gateway data transfer costs for other services

        return vpc

    def _create_cluster(self, vpc):
        """Create ECS cluster in the VPC"""
        return ecs.Cluster(
            self,
            "Cluster",
            vpc=vpc,
            container_insights=True,
        )

    def _create_task_role(self):
        """Create IAM role with Amazon Bedrock permissions for ECS tasks"""
        task_role = iam.Role(
            self, "TaskRole", assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )
        # Add Amazon Bedrock invoke permissions.
        # System-defined cross-region inference profiles (us.*, eu.*, global.* prefixes)
        # have no account ID in their ARN: arn:aws:bedrock:REGION::inference-profile/...
        # Customer-created application inference profiles do include the account ID.
        # Foundation models also have no account ID.
        # We include both patterns to cover all model types (Claude, Nova, Titan, etc.)
        # without reverting to Resource:*.
        guardrail_id = self.config.get("guardrail_id", "")
        bedrock_invoke_resources = [
            "arn:aws:bedrock:*::inference-profile/*",  # system-defined cross-region profiles
            f"arn:aws:bedrock:*:{self.account}:inference-profile/*",  # customer application profiles
            "arn:aws:bedrock:*::foundation-model/*",  # foundation models
        ]
        bedrock_invoke_policy = iam.PolicyStatement(
            actions=["bedrock:Invoke*", "bedrock:Converse*"],
            resources=bedrock_invoke_resources,
        )
        task_role.add_to_policy(bedrock_invoke_policy)

        if guardrail_id:
            task_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["bedrock:ApplyGuardrail"],
                    resources=[
                        f"arn:aws:bedrock:{self.region}:{self.account}:guardrail/{guardrail_id}"
                    ],
                )
            )

        # Add S3 permissions if S3 mode is enabled
        s3_bucket = self.config.get("codebase_artifacts", {}).get("bucket", "")
        kms_key_arn = self.config.get("codebase_artifacts", {}).get("kms_key_arn", "")

        if s3_bucket:
            s3_policy = iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[f"arn:aws:s3:::{s3_bucket}", f"arn:aws:s3:::{s3_bucket}/*"],
            )
            task_role.add_to_policy(s3_policy)

            # Add KMS decrypt permission if customer provides CMK
            if kms_key_arn:
                kms_policy = iam.PolicyStatement(
                    actions=["kms:Decrypt", "kms:DescribeKey"],
                    resources=[kms_key_arn],
                )
                task_role.add_to_policy(kms_policy)

        # Suppress NAG warnings for wildcard actions and cross-region model ARNs
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

        # Add S3 suppression if S3 mode is enabled
        if s3_bucket:
            nag_suppressions.append(
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "IRIS requires access to all objects in the specified S3 bucket for codebase artifacts",
                    "appliesTo": [f"Resource::arn:aws:s3:::{s3_bucket}/*"],
                }
            )

        self._suppress_nag(task_role.node.find_child("DefaultPolicy"), nag_suppressions)

        return task_role

    def _create_task_definition(self, task_role, user_pool, user_pool_client):
        """Create ECS task definition with sidecar pattern (frontend + backend)"""
        total_memory = self.config["resources"]["total_memory_mib"]
        total_cpu = self.config["resources"]["total_cpu"]

        task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            memory_limit_mib=total_memory,
            cpu=total_cpu,
            task_role=task_role,
        )

        # Calculate memory allocation
        backend_memory = int(
            total_memory
            * self.config["resources"]["backend"]["memory_percentage"]
            / 100
        )
        frontend_memory = int(
            total_memory
            * self.config["resources"]["frontend"]["memory_percentage"]
            / 100
        )

        retention_days = getattr(
            logs.RetentionDays,
            f"_{self.config['logging']['retention_days']}_DAYS",
            logs.RetentionDays.ONE_WEEK,
        )

        # Prepare frontend environment variables for Docker startup script
        frontend_env = {
            "DEPLOYMENT_MODE": "cloud",
            "REACT_APP_BACKEND_URL": "/api",
            "REACT_APP_WEBSOCKET_URL": "/ws",
            "STACK_NAME": self.stack_name,
            # Environment variables for injection script
            "AWS_REGION": self.region,
            "USER_POOL_ID": user_pool.user_pool_id,
            "USER_POOL_CLIENT_ID": user_pool_client.user_pool_client_id,
            # Also set REACT_APP versions for compatibility
            "REACT_APP_AWS_REGION": self.region,
            "REACT_APP_USER_POOL_ID": user_pool.user_pool_id,
            "REACT_APP_USER_POOL_CLIENT_ID": user_pool_client.user_pool_client_id,
        }

        # Frontend container - React app on port 3000 (ALB target) - ADD FIRST
        frontend_container = task_definition.add_container(
            "frontend",
            image=ecs.ContainerImage.from_asset(
                "../frontend",
                build_args={"BUILD_MODE": "cloud"},  # Use cloud mode for CDK deployment
                platform=assets.Platform.LINUX_AMD64,  # Use buildx for multi-platform
                exclude=[
                    "**/.venv",
                    "**/venv",
                    "**/__pycache__",
                    "**/cdk.out",
                    "**/.git",
                    "**/node_modules",
                    "**/*.pyc",
                    "**/.DS_Store",
                ],
            ),
            memory_reservation_mib=frontend_memory,
            environment=frontend_env,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="frontend", log_retention=retention_days
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:3000 || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(10),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )
        frontend_container.add_port_mappings(
            ecs.PortMapping(container_port=3000, protocol=ecs.Protocol.TCP)
        )

        # Determine if S3 mode is enabled
        s3_bucket = self.config.get("codebase_artifacts", {}).get("bucket", "")
        s3_prefix = self.config.get("codebase_artifacts", {}).get("prefix", "")
        use_s3_mode = bool(s3_bucket)

        # Backend environment variables
        backend_env = {
            "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
            "PYTHONPATH": "/app/src",
            "AWS_DEFAULT_REGION": self.region,
            "USER_POOL_ID": user_pool.user_pool_id,
            "USER_POOL_CLIENT_ID": user_pool_client.user_pool_client_id,
        }

        # Add S3 configuration if enabled
        if use_s3_mode:
            backend_env["S3_BUCKET"] = s3_bucket
            if s3_prefix:
                backend_env["S3_PREFIX"] = s3_prefix

        # Backend container - Python WebSocket server on port 8000
        backend_container = task_definition.add_container(
            "backend",
            image=ecs.ContainerImage.from_asset(
                "../",
                file="backend/Dockerfile_s3" if use_s3_mode else "backend/Dockerfile",
                platform=assets.Platform.LINUX_AMD64,  # Use buildx for multi-platform
                exclude=[
                    "**/.venv",
                    "**/venv",
                    "**/__pycache__",
                    "**/cdk.out",
                    "**/.git",
                    "**/node_modules",
                    "**/*.pyc",
                    "**/.DS_Store",
                ],
            ),
            memory_reservation_mib=backend_memory,
            environment=backend_env,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="backend", log_retention=retention_days
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(10),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )
        backend_container.add_port_mappings(
            ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
        )

        # Suppress NAG warning for environment variables
        self._suppress_nag(
            task_definition,
            [
                {
                    "id": "AwsSolutions-ECS2",
                    "reason": "Environment variables contain non-sensitive configuration values like region and paths",
                }
            ],
        )

        # Suppress NAG warning for ExecutionRole wildcard permissions
        self._suppress_nag(
            task_definition.execution_role.node.find_child("DefaultPolicy"),
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "ECS ExecutionRole requires wildcard permissions for ECR image pulls and CloudWatch Logs",
                    "appliesTo": ["Resource::*"],
                }
            ],
        )

        return task_definition

    def _create_service(self, cluster, task_definition):
        # Create S3 bucket for ALB access logs with server access logging
        alb_logs_bucket = s3.Bucket(
            self,
            "ALBLogsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            server_access_logs_bucket=self.server_access_logs_bucket,
            server_access_logs_prefix="alb-logs-access/",
        )

        # Create custom security group for ECS service with no default egress
        # This prevents the problematic behavior where CDK clears egress rules on stack updates
        ecs_security_group = ec2.SecurityGroup(
            self,
            "ServiceSecurityGroup",
            vpc=cluster.vpc,
            description="Security group for ECS service with least privilege egress",
            allow_all_outbound=False,  # Critical: prevents default 0.0.0.0/0 egress rule
        )

        # Add specific egress rules to the custom security group
        # Allow HTTPS (443) for VPC endpoints
        ecs_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(cluster.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS to VPC endpoints",
        )

        # Allow HTTPS (443) to internet for Cognito JWKS endpoint
        # Cognito does not have VPC endpoints, so we need internet access for JWT validation
        ecs_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS to Cognito for JWT validation (no VPC endpoint available)",
        )

        # Allow DNS (53) for name resolution
        ecs_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(cluster.vpc.vpc_cidr_block),
            connection=ec2.Port.udp(53),
            description="Allow DNS queries",
        )

        # Suppress NAG warning for ECS security group egress
        self._suppress_nag(
            ecs_security_group,
            [
                {
                    "id": "AwsSolutions-EC23",
                    "reason": "ECS tasks require HTTPS egress for Cognito JWT validation (no VPC endpoint available). All other traffic restricted to VPC endpoints.",
                }
            ],
        )

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Service",
            cluster=cluster,
            task_definition=task_definition,
            public_load_balancer=True,
            assign_public_ip=False,
            listener_port=80,
            desired_count=self.config["service"]["desired_count"],
            security_groups=[ecs_security_group],  # Use our custom security group
        )

        # Enable ALB access logging
        service.load_balancer.log_access_logs(
            bucket=alb_logs_bucket, prefix="alb-access-logs"
        )

        # Configure health check to target React frontend
        service.target_group.configure_health_check(
            path="/",
            port="3000",
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
            timeout=Duration.seconds(10),
            interval=Duration.seconds(30),
        )

        # SECURITY: Replace default internet access with CloudFront-only access
        # First remove the default 0.0.0.0/0 rule
        default_sg = service.load_balancer.connections.security_groups[0]

        # Get CloudFront prefix list for current region
        cloudfront_prefix_list = self._get_cloudfront_prefix_list()

        # Add CloudFront-only access rule
        default_sg.add_ingress_rule(
            peer=ec2.Peer.prefix_list(cloudfront_prefix_list),
            connection=ec2.Port.tcp(80),
            description="Allow CloudFront access only",
        )

        # Remove the default 0.0.0.0/0 rule by overriding it
        cfn_sg = default_sg.node.default_child
        cfn_sg.add_property_override(
            "SecurityGroupIngress",
            [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "SourcePrefixListId": cloudfront_prefix_list,
                    "Description": "Allow CloudFront access only",
                }
            ],
        )

        # Suppress NAG warning for ALB security group allowing 0.0.0.0/0
        self._suppress_nag(
            service.load_balancer.node.find_child("SecurityGroup"),
            [
                {
                    "id": "AwsSolutions-EC23",
                    "reason": "ALB needs to accept traffic from CloudFront edge locations globally, restricted by CloudFront prefix list",
                }
            ],
        )

        # Create target group for backend container
        backend_target_group = elbv2.ApplicationTargetGroup(
            self,
            "BackendTargetGroup",
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=service.cluster.vpc,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(path="/health", port="8000"),
        )

        # Register ECS service to backend target group
        backend_target_group.add_target(
            service.service.load_balancer_target(
                container_name="backend", container_port=8000
            )
        )

        # Route /ws and /api/* to backend container
        service.listener.add_action(
            "BackendAction",
            priority=100,
            conditions=[elbv2.ListenerCondition.path_patterns(["/ws*", "/api/*"])],
            action=elbv2.ListenerAction.forward([backend_target_group]),
        )

        return service

    def _create_cloudfront(self, service):
        """Create CloudFront distribution with default SSL certificate"""

        # Create S3 bucket for CloudFront access logs with server access logging
        cloudfront_logs_bucket = s3.Bucket(
            self,
            "CloudFrontLogsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
            server_access_logs_bucket=self.server_access_logs_bucket,
            server_access_logs_prefix="cloudfront-logs-access/",
        )

        # Configure origin with custom headers for ALB security
        origin = origins.LoadBalancerV2Origin(
            service.load_balancer,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            http_port=80,
            read_timeout=Duration.seconds(60),
            keepalive_timeout=Duration.seconds(5),
            origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2],
            custom_headers={
                "X-Forwarded-Proto": "https",
                "X-CloudFront-Origin": "true",  # Custom header to verify CloudFront origin
            },
        )

        behavior_options = {
            "origin": origin,
            "allowed_methods": cloudfront.AllowedMethods.ALLOW_ALL,
            "viewer_protocol_policy": cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,  # Force HTTPS
            "cache_policy": cloudfront.CachePolicy.CACHING_DISABLED,
            "origin_request_policy": cloudfront.OriginRequestPolicy.ALL_VIEWER,
            "response_headers_policy": cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
            "compress": False,
        }

        # CloudFront distribution with default SSL certificate (automatic)
        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_behavior=cloudfront.BehaviorOptions(**behavior_options),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=origin,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                    response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
                    compress=False,
                ),
                "/ws": cloudfront.BehaviorOptions(
                    origin=origin,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                    response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
                    compress=False,
                ),
            },
            enable_ipv6=False,
            enable_logging=True,
            log_bucket=cloudfront_logs_bucket,
            log_file_prefix="cloudfront-access-logs/",
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            comment="IRIS - CloudFront with default SSL",
        )

        # Suppress NAG warning for default CloudFront certificate TLS limitation
        self._suppress_nag(
            distribution,
            [
                {
                    "id": "AwsSolutions-CFR4",
                    "reason": "Default CloudFront certificate automatically uses TLSv1 minimum - custom certificate requires domain ownership",
                },
                {
                    "id": "AwsSolutions-CFR5",
                    "reason": "CloudFront to ALB communication uses HTTP over AWS internal network. HTTPS between CloudFront and ALB would require SSL certificate on ALB which needs domain ownership. End-user traffic is encrypted via HTTPS redirection to CloudFront.",
                },
            ],
        )

        return distribution

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

        # Suppress NAG warning for disabled advanced security mode
        self._suppress_nag(
            user_pool,
            [
                {
                    "id": "AwsSolutions-COG3",
                    "reason": "Advanced security mode disabled due to ESSENTIALS pricing tier limitation - threat protection features not supported",
                }
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

    def _create_outputs(self, distribution, service, user_pool, user_pool_client):
        """Create CloudFormation outputs for URLs and Cognito credentials"""
        CfnOutput(self, "CloudFrontURL", value=f"https://{distribution.domain_name}")
        CfnOutput(
            self,
            "LoadBalancerURL",
            value=f"http://{service.load_balancer.load_balancer_dns_name}",
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
