<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# System Architecture

This document provides a comprehensive overview of the IRIS system architecture, including AWS services, deployment patterns, security considerations, and scalability features.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [System Components](#system-components)
- [AWS Services](#aws-services)
- [Security Architecture](#security-architecture)
- [Data Flow](#data-flow)

## Architecture Overview

IRIS is built as a cloud-native application leveraging AWS services for scalability, security, and reliability. The system follows a microservices architecture with clear separation of concerns between frontend, backend, and AI processing components.

### High-Level Architecture

![Architecture Diagram](images/architecture.png)

### Key Architectural Principles

1. **Microservices Architecture**: Loosely coupled services with well-defined interfaces
2. **Cloud-Native Design**: Built for AWS with managed services
3. **Security by Design**: Multiple layers of security controls and encryption
4. **Event-Driven Processing**: Asynchronous processing for better performance
5. **Infrastructure as Code**: All infrastructure defined and managed through CDK
6. **Observability First**: Comprehensive logging, monitoring, and tracing

## System Components

### Frontend Layer

#### React Application

- **Technology**: React 18 (Vite build)
- **Hosting**: Static site in a private Amazon S3 bucket, served through Amazon CloudFront with Origin Access Control (OAC)
- **Features**:
  - Direct, streaming communication with the AgentCore Runtime over HTTPS (Server-Sent Events)
  - Responsive design for multiple devices
  - Client-side (SPA) routing, with Amazon CloudFront serving `/index.html` for 403/404 responses
  - State management for conversations and tool activity

#### Configuration Management

- **Runtime Configuration**: A `runtime-config.js` file is injected at deploy time with the AWS region, Amazon Cognito user pool id, Amazon Cognito app client id, and the AgentRuntimeArn
- **Environment-Specific Settings**: Development and cloud configurations
- **Feature Flags**: Conditional feature enablement

### Backend Layer

#### AgentCore Runtime

- **Technology**: Amazon Bedrock AgentCore Runtime — serverless and fully managed
- **Entrypoint**: `backend/agent_runtime.py`, which implements the AgentCore HTTP protocol contract: `POST /invocations` (single request/response, with SSE streaming for chat) and `GET /ping` (health check), listening on port 8080
- **Features**:
  - Streaming response handling over Server-Sent Events
  - Per-session isolation with no server infrastructure to manage
  - Automatic scaling and lifecycle management by the Runtime

#### Session Management

- **Implementation**: Each `runtimeSessionId` is served by its own isolated microVM (dedicated CPU, memory, and filesystem). A per-session Strands agent lives in process for the life of that microVM, and a small `session_id -> Agent` cache lets multi-turn conversations reuse the same in-memory history.
- **Features**:
  - Strong isolation between sessions (one microVM per session)
  - Session lifecycle managed by the AgentCore Runtime
  - In-memory conversation history for multi-turn chat
  - Concurrent sessions served independently

### AI Processing Layer

#### Agentic Framework

- **Technology**: Strands framework with Amazon Bedrock integration
- **Components**:
  - Main orchestrating agent
  - Specialized sub-agents (file retrieval, code search)
  - Tool-based architecture
  - Conversation management

#### Model Integration

- **Primary Models**: Claude (Haiku and Sonnet) via Amazon Bedrock
- **Features**:
  - Multi-model support for different tasks
  - Regional distribution for performance
  - Prompt caching for efficiency
  - Streaming response generation

### Data Layer

#### Codebase Storage

- **Primary**: S3 for artifact storage
- **Processing**: Local file system during analysis
- **Caching**: In-memory caching for frequently accessed data

#### Configuration Storage

- **Application Config**: YAML files in version control
- **Runtime Config**: Environment variables and the deploy-time-injected `runtime-config.js`
- **User Data**: Amazon Cognito for user accounts

## AWS Services

### Compute Services

#### Amazon Bedrock AgentCore Runtime

- **Purpose**: Serverless, fully managed hosting for the IRIS backend agent
- **Configuration**:
  - Each `runtimeSessionId` runs in its own isolated microVM with dedicated CPU, memory, and filesystem
  - `networkMode` = `PUBLIC`, `protocol` = `HTTP`
  - Built from an ARM64 container image (the Runtime requires ARM64)
  - Health checks via `GET /ping`; the Runtime handles scaling and session lifecycle

#### AWS Lambda

- **Purpose**: A CDK-managed helper Lambda backs the S3 auto-delete custom resource used when the stack is torn down. A Cognito pre-signup validation Lambda is created only when self-signup is enabled.
- **Note**: Self-signup is disabled by default; users are created via console

### Storage Services

#### Amazon S3

- **Buckets** (created by the stack):
  - **FrontendBucket**: Private bucket holding the built React app, served through Amazon CloudFront via OAC
  - **FrontendCloudFrontLogsBucket**: Amazon CloudFront access logs for the frontend distribution
  - **ServerAccessLogsBucket**: S3 server access logs for the other buckets
- **External bucket**: The codebase artifacts bucket (`codebase_artifacts.bucket` in `infra/config.yaml`) is pre-existing/external and is read by the Runtime in S3 mode; it is not created by the stack.
- **Features**:
  - Server-side encryption (SSE-S3)
  - Block Public Access enabled on all buckets
  - Versioning enabled
  - TLS/HTTPS enforced via bucket policy (`enforce_ssl=True`)

### Networking Services

The backend runs on the AgentCore Runtime in `PUBLIC` network mode, so IRIS does not provision or manage any customer VPC, subnets, NAT gateways, load balancers, or security groups. Network access to the Runtime is gated by its built-in Amazon Cognito JWT authorizer.

#### Amazon CloudFront

- **Purpose**: Global content delivery network for the static frontend
- **Features**:
  - Global edge locations for low latency
  - Private S3 origin secured with Origin Access Control (OAC)
  - `REDIRECT_TO_HTTPS` viewer protocol policy and the managed `SECURITY_HEADERS` response headers policy
  - TLS 1.2 (2021) minimum protocol version
  - SPA routing: 403/404 responses return `/index.html` with a 200 status
  - Access logging to a dedicated S3 bucket

#### AgentCore Runtime Data-Plane Endpoint

- **Purpose**: The browser invokes the AgentCore Runtime directly over HTTPS at the AWS data-plane endpoint (`https://bedrock-agentcore.{region}.amazonaws.com`)
- **Features**:
  - `POST /runtimes/{arn}/invocations?qualifier=DEFAULT` returns a Server-Sent Events stream for chat
  - Cross-origin responses are handled by the AWS data-plane endpoint itself (it returns `access-control-allow-origin: *`), so the application never handles CORS
  - TLS for all traffic

### Security Services

#### Amazon Cognito

- **Components**:
  - **User Pool** (`IrisUserPool`): User authentication and management
  - **User Pool Client** (`IrisClient`): Public client (no secret) used by the frontend; the app client id is the `allowedClients` value for the Runtime's JWT authorizer
- **Features**:
  - Email- and username-based sign-in
  - Email verification
  - Password policy (minimum length and character-class requirements)
  - The AgentCore Runtime's built-in JWT authorizer validates Cognito access tokens before requests reach the container

#### AWS IAM

- **Roles and Policies**:
  - **AgentCore Execution Role**: Trusts `bedrock-agentcore.amazonaws.com`; grants Amazon Bedrock invoke (`bedrock:Invoke*`, `bedrock:Converse*`) plus optional Bedrock guardrail and optional Amazon S3 read (for the codebase artifacts bucket in S3 mode). CloudWatch Logs, AWS X-Ray, and AgentCore workload-identity permissions are added by the AgentCore Runtime L2 construct.
  - **S3 Auto-Delete Custom Resource Role**: Used by the CDK helper Lambda that empties buckets on stack deletion
  - **Lambda Execution Role**: Permissions for the Cognito pre-signup function (only if self-signup enabled)
- **Security Features**:
  - Least privilege access
  - Temporary credentials
  - Resource-scoped policies where the service supports it

### AI/ML Services

#### Amazon Bedrock

- **Models**:
  - **Claude Haiku**: Fast responses and file processing
  - **Claude Sonnet**: Complex reasoning and code generation
- **Features**:
  - Multiple regions for performance and availability
  - Prompt caching for efficiency
  - Streaming responses for real-time interaction
  - Model versioning and updates

### Monitoring Services

#### Amazon CloudWatch

- **Metrics**: The AgentCore Runtime emits its own service metrics to CloudWatch. IRIS
  does not define custom metrics, alarms, or dashboards in the stack.
- **Logging**:
  - Application logs from the AgentCore Runtime (`/aws/bedrock-agentcore/runtimes/*`)
  - AWS X-Ray traces from the Runtime
  - Amazon CloudFront access logs (stored in S3)

## Deployment Architecture

### Infrastructure as Code

#### AWS CDK Implementation

- **Language**: Python
- **Structure**:
  ```
  infra/
  ├── app.py                  # CDK application entry point
  ├── stack.py                # Main stack definition
  ├── config.yaml             # Infrastructure configuration
  ├── cdk.json                # CDK project configuration
  ├── requirements.txt        # Python dependencies
  └── lambda/                 # Lambda functions (only if self-signup enabled)
      └── cognito_auth/       # Cognito pre-signup validation
          └── pre_signup_lambda.py
  ```

### Container Strategy

#### Backend Container Image

The backend is packaged as a single ARM64 container image that runs the AgentCore Runtime entrypoint (`backend/agent_runtime.py`) on port 8080. Two build variants are provided:

- **`backend/Dockerfile.agentcore`** (bake-in mode): the codebase and its pre-generated representation are baked into the image at build time.
- **`backend/Dockerfile.agentcore_s3`** (S3 mode): the image downloads the codebase index from Amazon S3 at boot via `backend/startup-s3-agentcore.sh`.

The CDK `AgentRuntimeArtifact.from_asset(..., platform=LINUX_ARM64)` builds the image (the Runtime requires ARM64).

#### Container Configuration

```yaml
# Backend AgentCore Runtime container
Image: ARM64, port 8080 (POST /invocations + GET /ping)
Environment Variables:
  - AWS_DEFAULT_REGION
  - S3_BUCKET (if S3 mode enabled)
  - S3_PREFIX (if S3 mode enabled)
```

The frontend is not containerized: the React app is built with Vite and uploaded to the private `FrontendBucket`, then served through Amazon CloudFront.

## Security Architecture

### Defense in Depth

#### Network Security

1. **Managed Runtime Boundary**: The backend runs on the AgentCore Runtime in `PUBLIC` network mode; there is no customer VPC, subnet, NAT gateway, load balancer, or security group to manage.
2. **Authorizer-Gated Access**: The Runtime's built-in Amazon Cognito JWT authorizer validates tokens before any request reaches the container.
3. **Private Frontend Origin**: The S3 frontend bucket is private and reachable only through Amazon CloudFront via Origin Access Control (OAC).
4. **HTTPS Everywhere**: TLS is enforced for the CloudFront distribution and for the AgentCore data-plane endpoint.

#### Application Security

1. **Authentication**: Cognito-based user authentication
2. **Authorization**: Role-based access control
3. **Input Validation**: Comprehensive input sanitization
4. **Output Encoding**: XSS prevention measures

#### Data Security

1. **Encryption at Rest**: S3 encryption
2. **Encryption in Transit**: TLS for all communications
3. **Key Management**: AWS KMS for encryption keys
4. **Data Classification**: Sensitive data identification and handling

### Security Controls

#### Access Control

- **Amazon CloudFront**: Public access to the static frontend
- **AgentCore Runtime**: Reachable via the AWS data-plane endpoint; every invocation must carry a valid Amazon Cognito access token, which the Runtime's JWT authorizer verifies before the request reaches the container
- **S3 Buckets**: Private, no public access; the frontend bucket is reachable only through Amazon CloudFront (OAC)
- **Amazon Cognito**: User authentication (users created via console)

## Data Flow

### Request Processing Flow

#### Frontend Delivery Flow

```
Browser → Amazon CloudFront (OAC) → Private S3 FrontendBucket → Static React App
```

#### User Authentication Flow

```
Browser → Amazon Cognito (sign in) → Access Token → Bearer token on AgentCore invocations
```

#### Chat Communication Flow

```
Browser → AgentCore data-plane endpoint (Cognito JWT authorizer) → microVM (agent_runtime.py) → Agent Processing → Amazon Bedrock → SSE Response Stream
```

#### File Processing Flow

```
S3 Artifacts (or baked-in index) → microVM filesystem → File Analysis → Agent Processing → Response Generation
```

### Data Processing Pipeline

#### Codebase Analysis Pipeline

1. **Ingestion**: Codebase uploaded to S3 or processed locally
2. **Discovery**: File system analysis and tree generation
3. **Processing**: Parallel file summarization using multiple Amazon Bedrock models
4. **Indexing**: Context generation and relationship mapping
5. **Storage**: Processed artifacts stored in S3 (if S3 mode) or locally
6. **Caching**: Frequently accessed data cached in memory

#### Real-time Query Processing

1. **Query Reception**: User query received by `POST /invocations` on the AgentCore Runtime
2. **Context Loading**: Relevant codebase context loaded
3. **Agent Orchestration**: Specialized agents selected and coordinated
4. **Model Interaction**: Amazon Bedrock models called for processing
5. **Response Streaming**: Response streamed back to the browser as Server-Sent Events
6. **Session Management**: Conversation state maintained in the per-session microVM

## Related Documentation

- [Deployment Guide](deployment-guide.md) - Detailed deployment instructions
- [Development Guide](dev-guide.md) - Development setup and workflows
- [Agentic Architecture](agentic-architecture.md) - AI agent architecture details
- [MCP Integration](mcp.md) - Model Context Protocol integration

## External References

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [AWS Security Best Practices](https://aws.amazon.com/security/security-learning/)
