# Comprehensive Threat Model Report

**Generated**: 2026-04-29
**Current Phase**: Completed — POC Release Review
**Overall Completion**: 90.0%

> **POC Notice**: This project is a proof-of-concept demonstration. Several threats below are accepted risks at this stage and documented for awareness. This threat model reflects the current state of the codebase and the mitigations implemented prior to open-source release.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Business Context](#business-context)
3. [System Architecture](#system-architecture)
4. [Threat Actors](#threat-actors)
5. [Trust Boundaries](#trust-boundaries)
6. [Assets and Flows](#assets-and-flows)
7. [Threats](#threats)
8. [Mitigations](#mitigations)
9. [Assumptions](#assumptions)
10. [Phase Progress](#phase-progress)

## Executive Summary

IRIS is a cloud-native AI-powered code analysis and chat application built on AWS. It allows users to upload codebases to Amazon S3, generates summaries and context using Amazon Bedrock LLMs (Claude models), and provides a real-time WebSocket-based chat interface for querying code. The system uses a React frontend served via Amazon CloudFront, a FastAPI WebSocket backend on Amazon ECS on AWS Fargate, Amazon Cognito for authentication, Amazon S3 for codebase storage, and Amazon DynamoDB for optional conversation logging. It also exposes an MCP server for IDE integration.

### Key Statistics

- **Total Threats**: 13
- **Total Mitigations**: 10
- **Total Assumptions**: 4
- **System Components**: 10
- **Assets**: 13
- **Threat Actors**: 13

### Threat-to-Mitigation Summary

| #   | Threat                                                         | Severity | Mitigation                                                                                                                                                   |
| --- | -------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| T1  | Auth bypass when Cognito is not configured (local/Docker only) | Low      | CDK enforces Cognito in cloud deployments; only affects local dev. **POC accepted risk.**                                                                    |
| T2  | Prompt injection via agentic framework                         | Critical | ✅ Partially mitigated: Amazon Bedrock Guardrails + trust-hierarchy markers in system prompts (`[BEGIN/END UNTRUSTED FILE DATA]`) + file allowlist filtering |
| T3  | Direct S3 bucket access via misconfigured policies             | Critical | Block public access, restrict to ECS task role, VPC endpoint policies                                                                                        |
| T4  | HTTP interception between CloudFront and ALB                   | Medium   | Relies on AWS Nitro System physical encryption                                                                                                               |
| T5  | XSS via unsafe-inline/unsafe-eval CSP                          | High     | ✅ Fixed: removed `rehype-raw`, DOMPurify sanitization added                                                                                                 |
| T6  | JWT token replay / session hijacking                           | High     | ✅ Mitigated: JWKS TTL cache with proactive refresh, monotonic session TTL (1h), session cap (100 max)                                                       |
| T7  | ECS task role credential theft                                 | Critical | ✅ Fixed: Amazon Bedrock IAM scoped to inference profiles + foundation model ARNs; Guardrail permission scoped to specific ARN                               |
| T8  | Log injection / repudiation                                    | Medium   | Partially mitigated by existing `sanitize_for_log`. **POC accepted risk.**                                                                                   |
| T9  | MCP server path traversal                                      | Medium   | ✅ Fixed: path containment check (`resolve().relative_to()`) in `read_multiple_files`; MCP command allowlist (deferred)                                      |
| T10 | WebSocket DoS / Amazon Bedrock cost escalation                 | High     | ✅ Fixed: token-bucket rate limiter (10 msg/min), session cap (100), 64KB message size limit                                                                 |
| T11 | Missing RBAC / cross-tenant access                             | High     | **POC accepted risk** — single-tenant deployment assumed. Multi-tenant RBAC deferred.                                                                        |
| T12 | Amazon DynamoDB conversation data exposure                     | Medium   | CMK encryption optional; conversation history file permissions restricted to owner (0o600). **POC accepted risk.**                                           |
| T13 | Supply chain dependency compromise                             | High     | pip-audit in CI/CD, pinned deps with hashes, Dependabot                                                                                                      |

## Business Context

**Description**: IRIS is a cloud-native AI-powered code analysis and chat application built on AWS. It allows users to upload codebases to Amazon S3, generates summaries and context using Amazon Bedrock LLMs (Claude models), and provides a real-time WebSocket-based chat interface for querying code. The system uses a React frontend served via Amazon CloudFront, a FastAPI WebSocket backend on Amazon ECS on AWS Fargate, Amazon Cognito for authentication, Amazon S3 for codebase storage, and Amazon DynamoDB for optional conversation logging. It also exposes an MCP server for IDE integration.

### Business Features

- **Industry Sector**: Technology
- **Data Sensitivity**: Confidential
- **User Base Size**: Medium
- **Geographic Scope**: Multinational
- **Regulatory Requirements**: Multiple
- **System Criticality**: High
- **Financial Impact**: High
- **Authentication Requirement**: Federated
- **Deployment Environment**: Cloud-Public
- **Integration Complexity**: Complex

## System Architecture

### Components

| ID   | Name                               | Type     | Service Provider | Description                                                                                                                                                                                                                                            |
| ---- | ---------------------------------- | -------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| C001 | React Frontend                     | Compute  | AWS              | React 18+ TypeScript SPA served via CloudFront CDN with S3 origin. Handles real-time WebSocket communication, client-side routing, and state management.                                                                                               |
| C002 | Application Load Balancer          | Network  | AWS              | Application Load Balancer providing SSL termination, WebSocket support, and routing to Amazon ECS on AWS Fargate tasks. Ingress restricted to Amazon CloudFront prefix list on port 80.                                                                |
| C003 | FastAPI WebSocket Server           | Compute  | AWS              | FastAPI backend running on Amazon ECS on AWS Fargate in private subnets. Handles WebSocket connections, session management, JWT authentication via Amazon Cognito, and orchestrates AI agent interactions. Runs as non-root user in container.         |
| C004 | Amazon Bedrock                     | Compute  | AWS              | Amazon Bedrock LLM service providing Claude model inference. Used for code analysis, summarization, and agentic chat. Supports prompt caching and streaming responses. Accessed via IAM task role.                                                     |
| C005 | Amazon S3 Codebase Bucket          | Storage  | AWS              | Customer-owned Amazon S3 bucket storing codebase artifacts and analysis outputs. SSE-S3 encryption enforced, optional CMK support. Accessed by Amazon ECS tasks via VPC endpoint.                                                                      |
| C006 | Amazon DynamoDB Conversation Store | Storage  | AWS              | Optional Amazon DynamoDB table for persisting conversation history. Async logging to avoid blocking agent. Messages truncated at 8.5KB. Encrypted with AWS-owned keys by default.                                                                      |
| C007 | VPC Network                        | Network  | AWS              | Amazon VPC (10.0.0.0/16) with public subnets (Application Load Balancer) and private subnets (Amazon ECS) across 2 AZs. NAT Gateway for outbound. VPC endpoints for Amazon S3, Amazon Bedrock, Amazon CloudWatch, Amazon ECR. Port 25 blocked.         |
| C008 | Amazon Cognito                     | Security | AWS              | Amazon Cognito User Pool providing JWT-based authentication (RS256). Issues access and ID tokens. Self-signup disabled by default. JWKS endpoint used for token verification.                                                                          |
| C009 | Amazon CloudWatch Logs             | Other    | AWS              | Amazon CloudWatch Logs for application events, errors, authentication logs. Application Load Balancer and Amazon CloudFront access logs stored in Amazon S3. VPC Flow Logs for network traffic. Default 7-day retention, configurable up to 3650 days. |
| C010 | MCP Server                         | Compute  | Other            | Local MCP server exposing codebase_context and codebase_query tools for IDE integration. Runs as a local process, communicates via stdio. Provides path validation and configurable tool enablement.                                                   |

### Connections

| ID    | Source | Destination | Protocol | Port | Encrypted | Description                                                                                                    |
| ----- | ------ | ----------- | -------- | ---- | --------- | -------------------------------------------------------------------------------------------------------------- |
| CN001 | C001   | C001        | HTTPS    | 443  | Yes       | Users access React frontend via CloudFront CDN over HTTPS with TLS 1.2+                                        |
| CN002 | C001   | C002        | HTTP     | 80   | No        | CloudFront routes WebSocket and API traffic to ALB over HTTP on AWS internal network (Nitro System encryption) |
| CN003 | C002   | C003        | HTTP     | 8000 | No        | ALB forwards traffic to FastAPI WebSocket server on ECS Fargate in private subnets                             |
| CN004 | C003   | C004        | HTTPS    | 443  | Yes       | FastAPI server invokes Amazon Bedrock models for code analysis, summarization, and chat via VPC endpoint       |
| CN005 | C003   | C008        | HTTPS    | 443  | Yes       | FastAPI server validates JWT tokens against Amazon Cognito JWKS endpoint                                       |
| CN006 | C003   | C005        | HTTPS    | 443  | Yes       | FastAPI server reads/writes codebase artifacts from customer Amazon S3 bucket via VPC endpoint                 |
| CN007 | C003   | C006        | HTTPS    | 443  | Yes       | FastAPI server logs conversation history to Amazon DynamoDB (optional, async)                                  |
| CN008 | C003   | C009        | HTTPS    | 443  | Yes       | FastAPI server sends application logs to Amazon CloudWatch via VPC endpoint                                    |

### Data Stores

| ID   | Name                                 | Type           | Classification | Encrypted at Rest | Description                                                                                                                                                           |
| ---- | ------------------------------------ | -------------- | -------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D001 | S3 Codebase Artifacts                | Object Storage | Confidential   | Yes               | Customer-owned S3 bucket storing uploaded codebases, analysis artifacts, and codebase representations. SSE-S3 enforced, optional CMK.                                 |
| D002 | Amazon DynamoDB Conversation History | NoSQL          | Internal       | Yes               | Optional Amazon DynamoDB table storing conversation history between users and AI agents. Messages truncated at 8.5KB. Encrypted with AWS-owned keys by default.       |
| D003 | In-Memory Session Store              | Other          | Internal       | No                | In-memory session hashmap on ECS Fargate containers. Stores active WebSocket sessions, agent instances, user info, and conversation state. Lost on container restart. |
| D004 | Local File Cache                     | Other          | Internal       | No                | Local file cache (.iris_cache/) storing file hashes and codebase overview data for performance optimization. Deleted files cleaned automatically.               |

## Threat Actors

### Insider

- **Type**: ThreatActorType.INSIDER
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial, Revenge
- **Resources**: ResourceLevel.LIMITED
- **Relevant**: Yes
- **Priority**: 5/10
- **Description**: An employee or contractor with legitimate access to the system

### External Attacker

- **Type**: ThreatActorType.EXTERNAL
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 3/10
- **Description**: An external individual or group attempting to gain unauthorized access

### Nation-state Actor

- **Type**: ThreatActorType.NATION_STATE
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Espionage, Political
- **Resources**: ResourceLevel.EXTENSIVE
- **Relevant**: Yes
- **Priority**: 1/10
- **Description**: A government-sponsored group with advanced capabilities

### Hacktivist

- **Type**: ThreatActorType.HACKTIVIST
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Ideology, Political
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 6/10
- **Description**: An individual or group motivated by ideological or political beliefs

### Organized Crime

- **Type**: ThreatActorType.ORGANIZED_CRIME
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Financial
- **Resources**: ResourceLevel.EXTENSIVE
- **Relevant**: Yes
- **Priority**: 2/10
- **Description**: A criminal organization with significant resources

### Competitor

- **Type**: ThreatActorType.COMPETITOR
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial, Espionage
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 7/10
- **Description**: A business competitor seeking competitive advantage

### Script Kiddie

- **Type**: ThreatActorType.SCRIPT_KIDDIE
- **Capability Level**: CapabilityLevel.LOW
- **Motivations**: Curiosity, Reputation
- **Resources**: ResourceLevel.LIMITED
- **Relevant**: Yes
- **Priority**: 9/10
- **Description**: An inexperienced attacker using pre-made tools

### Disgruntled Employee

- **Type**: ThreatActorType.DISGRUNTLED_EMPLOYEE
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Revenge
- **Resources**: ResourceLevel.LIMITED
- **Relevant**: Yes
- **Priority**: 4/10
- **Description**: A current or former employee with a grievance

### Privileged User

- **Type**: ThreatActorType.PRIVILEGED_USER
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Financial, Accidental
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 8/10
- **Description**: A user with elevated privileges who may abuse them or make mistakes

### Third Party

- **Type**: ThreatActorType.THIRD_PARTY
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial, Accidental
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 10/10
- **Description**: A vendor, partner, or service provider with access to the system

### Malicious Authenticated User

- **Type**: ThreatActorType.INSIDER
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial, Espionage
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 2/10
- **Description**: Authenticated user who attempts to access other users' sessions, codebases, or escalate privileges beyond their authorization level.

### Prompt Injection Attacker

- **Type**: ThreatActorType.EXTERNAL
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Espionage, Financial
- **Resources**: ResourceLevel.LIMITED
- **Relevant**: Yes
- **Priority**: 1/10
- **Description**: Attacker who crafts malicious prompts to manipulate the LLM into revealing source code, system prompts, or executing unintended actions via the agentic framework.

### External Network Attacker

- **Type**: ThreatActorType.EXTERNAL
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Financial, Disruption
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 3/10
- **Description**: External attacker targeting the WebSocket endpoint, CloudFront distribution, or ALB to gain unauthorized access or disrupt service.

## Trust Boundaries

### Trust Zones

#### Internet

- **Trust Level**: TrustLevel.UNTRUSTED
- **Description**: The public internet, considered untrusted

#### DMZ

- **Trust Level**: TrustLevel.LOW
- **Description**: Demilitarized zone for public-facing services

#### Application

- **Trust Level**: TrustLevel.MEDIUM
- **Description**: Zone containing application servers and services

#### Data

- **Trust Level**: TrustLevel.HIGH
- **Description**: Zone containing databases and data storage

#### Admin

- **Trust Level**: TrustLevel.FULL
- **Description**: Administrative zone with highest privileges

#### External / Internet

- **Trust Level**: TrustLevel.UNTRUSTED
- **Description**: Public internet where end users access the application via CloudFront HTTPS endpoint

#### DMZ / Edge Layer

- **Trust Level**: TrustLevel.MEDIUM
- **Description**: AWS-managed CDN and load balancing layer. CloudFront distribution and ALB in public subnets.

#### AWS Managed Services

- **Trust Level**: TrustLevel.HIGH
- **Description**: AWS managed services accessed via VPC endpoints or IAM roles: Amazon Bedrock, Amazon S3, Amazon DynamoDB, Amazon CloudWatch, Amazon Cognito

#### Local Developer Environment

- **Trust Level**: TrustLevel.MEDIUM
- **Description**: Local developer machine running MCP server for IDE integration. Communicates via stdio, no network exposure.

#### Application Layer (Private VPC)

- **Trust Level**: TrustLevel.HIGH
- **Description**: Private VPC subnets containing ECS Fargate tasks running the FastAPI WebSocket server. No direct internet access.

### Trust Boundaries

#### Internet Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Web Application Firewall, DDoS Protection, TLS Encryption
- **Description**: Boundary between the internet and internal systems

#### DMZ Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Network Firewall, Intrusion Detection System, API Gateway
- **Description**: Boundary between public-facing services and internal applications

#### Data Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Database Firewall, Encryption, Access Control Lists
- **Description**: Boundary protecting data storage systems

#### Admin Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Privileged Access Management, Multi-Factor Authentication, Audit Logging
- **Description**: Boundary for administrative access

#### Internet to Edge Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: CloudFront WAF, HTTPS enforcement, TLS 1.2+, Security headers
- **Description**: Boundary between public internet and AWS edge layer (CloudFront/ALB). All traffic must be HTTPS.

#### Edge to Application Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Security groups (ALB-only ingress), Private subnets, No direct internet access
- **Description**: Boundary between DMZ (ALB in public subnets) and application layer (ECS in private subnets). Security groups restrict access.

#### Application to AWS Services Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: VPC endpoints, IAM task roles, TLS 1.2+, Least privilege policies
- **Description**: Boundary between application containers and AWS managed services. All access via VPC endpoints and IAM roles.

## Assets and Flows

### Assets

| ID   | Name                              | Type                 | Classification                   | Sensitivity | Criticality | Owner |
| ---- | --------------------------------- | -------------------- | -------------------------------- | ----------- | ----------- | ----- |
| A001 | User Credentials                  | AssetType.CREDENTIAL | AssetClassification.CONFIDENTIAL | 5           | 5           | N/A   |
| A002 | Personal Identifiable Information | AssetType.DATA       | AssetClassification.CONFIDENTIAL | 4           | 4           | N/A   |
| A003 | Session Token                     | AssetType.TOKEN      | AssetClassification.CONFIDENTIAL | 5           | 5           | N/A   |
| A004 | Configuration Data                | AssetType.CONFIG     | AssetClassification.INTERNAL     | 3           | 4           | N/A   |
| A005 | Encryption Keys                   | AssetType.KEY        | AssetClassification.RESTRICTED   | 5           | 5           | N/A   |
| A006 | Public Content                    | AssetType.DATA       | AssetClassification.PUBLIC       | 1           | 2           | N/A   |
| A007 | Audit Logs                        | AssetType.DATA       | AssetClassification.INTERNAL     | 3           | 4           | N/A   |
| A008 | Customer Source Code              | AssetType.DATA       | AssetClassification.CONFIDENTIAL | 5           | 5           | N/A   |
| A009 | JWT Authentication Tokens         | AssetType.CREDENTIAL | AssetClassification.CONFIDENTIAL | 5           | 4           | N/A   |
| A010 | Conversation History              | AssetType.DATA       | AssetClassification.INTERNAL     | 4           | 3           | N/A   |
| A011 | LLM Prompts and Responses         | AssetType.DATA       | AssetClassification.INTERNAL     | 4           | 3           | N/A   |
| A012 | IAM Task Role Credentials         | AssetType.CREDENTIAL | AssetClassification.RESTRICTED   | 5           | 5           | N/A   |
| A013 | Application Configuration         | AssetType.DATA       | AssetClassification.INTERNAL     | 3           | 2           | N/A   |

### Asset Flows

| ID   | Asset                             | Source | Destination | Protocol | Encrypted | Risk Level |
| ---- | --------------------------------- | ------ | ----------- | -------- | --------- | ---------- |
| F001 | User Credentials                  | C001   | C002        | HTTPS    | Yes       | 4          |
| F002 | Session Token                     | C002   | C001        | HTTPS    | Yes       | 3          |
| F003 | Personal Identifiable Information | C003   | C004        | TLS      | Yes       | 3          |
| F004 | Audit Logs                        | C003   | C005        | TLS      | Yes       | 2          |
| F005 | Customer Source Code              | C005   | C003        | HTTPS    | Yes       | 4          |
| F006 | LLM Prompts and Responses         | C003   | C004        | HTTPS    | Yes       | 4          |
| F007 | JWT Authentication Tokens         | C001   | C003        | HTTPS    | Yes       | 5          |
| F008 | Conversation History              | C003   | C006        | HTTPS    | Yes       | 3          |

## Threats

### Identified Threats

#### T1: An unauthenticated attacker (local/Docker only)

**Statement**: An unauthenticated attacker, when running the system locally or via Docker without Cognito environment variables configured, can access the system without authentication since the backend falls back to anonymous mode. In cloud (CDK) deployments, Cognito is always provisioned and injected into the ECS task, so this threat does not apply to production.

- **Prerequisites**: when running locally or via Docker without Cognito environment variables (USER_POOL_ID, USER_POOL_CLIENT_ID) configured
- **Action**: access the system without authentication since the backend falls back to anonymous mode, granting default claims (sub: anonymous)
- **Impact**: complete unauthenticated access to all system features including codebase analysis and chat capabilities (local/dev environment only)
- **Severity**: Low (production not affected — CDK always provisions Cognito)
- **Impacted Assets**: A009
- **Tags**: authentication, misconfiguration, bypass

#### T2: An authenticated user

**Statement**: A An authenticated user with authenticated access to the WebSocket chat interface can craft malicious prompts to manipulate the LLM agent into revealing system prompts, accessing unauthorized files via the file retrieval agent, or executing unintended tool calls through the agentic framework, which leads to unauthorized access to customer source code, exfiltration of system prompts, or unintended information disclosure via agent tool calls

- **Prerequisites**: with authenticated access to the WebSocket chat interface
- **Action**: craft malicious prompts to manipulate the LLM agent into revealing system prompts, accessing unauthorized files via the file retrieval agent, or executing unintended tool calls through the agentic framework
- **Impact**: unauthorized access to customer source code, exfiltration of system prompts, or unintended information disclosure via agent tool calls
- **Impacted Assets**: A008, A011
- **Tags**: prompt-injection, LLM, agentic

#### T3: An insider or external attacker

**Statement**: A An insider or external attacker with access to the AWS account or misconfigured S3 bucket policies can access the S3 codebase artifacts bucket directly, bypassing application-level controls, due to overly permissive bucket policies or IAM permissions, which leads to direct access to all customer source code stored in the S3 bucket, bypassing all application security controls

- **Prerequisites**: with access to the AWS account or misconfigured S3 bucket policies
- **Action**: access the S3 codebase artifacts bucket directly, bypassing application-level controls, due to overly permissive bucket policies or IAM permissions
- **Impact**: direct access to all customer source code stored in the S3 bucket, bypassing all application security controls
- **Impacted Assets**: A008
- **Tags**: S3, data-exposure, misconfiguration

#### T4: An attacker with access to AWS internal network

**Statement**: A An attacker with access to AWS internal network with ability to intercept traffic between CloudFront and ALB can intercept unencrypted HTTP traffic between CloudFront and ALB (which uses HTTP over AWS internal network) to capture JWT tokens, user queries, or code analysis results, which leads to exposure of authentication tokens, user queries containing sensitive code context, and AI-generated responses

- **Prerequisites**: with ability to intercept traffic between CloudFront and ALB
- **Action**: intercept unencrypted HTTP traffic between CloudFront and ALB (which uses HTTP over AWS internal network) to capture JWT tokens, user queries, or code analysis results
- **Impact**: exposure of authentication tokens, user queries containing sensitive code context, and AI-generated responses
- **Tags**: TLS, encryption-in-transit, internal-network

#### T5: An attacker

**Statement**: A An attacker with ability to exploit unsafe-inline and unsafe-eval CSP directives in the frontend can inject malicious JavaScript via the chat interface that executes in other users' browsers, leveraging the CSP's unsafe-inline and unsafe-eval directives, which leads to theft of JWT tokens, session hijacking, or manipulation of the chat interface to display misleading AI responses

- **Prerequisites**: with ability to exploit unsafe-inline and unsafe-eval CSP directives in the frontend
- **Action**: inject malicious JavaScript via the chat interface that executes in other users' browsers, leveraging the CSP's unsafe-inline and unsafe-eval directives
- **Impact**: theft of JWT tokens, session hijacking, or manipulation of the chat interface to display misleading AI responses
- **Tags**: XSS, CSP, frontend

#### T6: An external attacker

**Statement**: A An external attacker with access to a stolen or leaked JWT token can replay the JWT token to establish a WebSocket connection and impersonate the legitimate user's session, which leads to full access to the impersonated user's session, including their codebase analysis results and conversation history

- **Prerequisites**: with access to a stolen or leaked JWT token
- **Action**: replay the JWT token to establish a WebSocket connection and impersonate the legitimate user's session
- **Impact**: full access to the impersonated user's session, including their codebase analysis results and conversation history
- **Impacted Assets**: A009
- **Tags**: session-hijacking, JWT, WebSocket

#### T7: An attacker

**Statement**: A An attacker with code execution inside the Amazon ECS container (e.g., via container escape or supply chain attack) can access the ECS task role credentials from the container metadata service to gain direct access to Amazon Bedrock, Amazon S3, Amazon DynamoDB, and AWS KMS, which leads to full access to all AWS services the task role can access, including customer source code in Amazon S3 and Amazon Bedrock model invocation

- **Prerequisites**: with code execution inside the Amazon ECS container (e.g., via container escape or supply chain attack)
- **Action**: access the ECS task role credentials from the container metadata service to gain direct access to Amazon Bedrock, Amazon S3, Amazon DynamoDB, and AWS KMS
- **Impact**: full access to all AWS services the task role can access, including customer source code in Amazon S3 and Amazon Bedrock model invocation
- **Impacted Assets**: A012
- **Tags**: IAM, credential-theft, container

#### T8: A malicious user

**Statement**: A A malicious user with authenticated access to the system can inject crafted input to create misleading log entries or deny performing actions when audit trails are insufficient, which leads to inability to attribute malicious actions to specific users, corrupted audit trails, or false log entries that mislead incident response

- **Prerequisites**: with authenticated access to the system
- **Action**: inject crafted input to create misleading log entries or deny performing actions when audit trails are insufficient
- **Impact**: inability to attribute malicious actions to specific users, corrupted audit trails, or false log entries that mislead incident response
- **Tags**: logging, log-injection, audit

#### T9: A malicious IDE plugin or compromised MCP client

**Statement**: A A malicious IDE plugin or compromised MCP client with access to the local developer machine running the MCP server can exploit the MCP server's codebase_context or codebase_query tools to access files outside the intended codebase directory via path traversal, which leads to access to sensitive files on the developer's machine beyond the intended codebase scope

- **Prerequisites**: with access to the local developer machine running the MCP server
- **Action**: exploit the MCP server's codebase_context or codebase_query tools to access files outside the intended codebase directory via path traversal
- **Impact**: access to sensitive files on the developer's machine beyond the intended codebase scope
- **Impacted Assets**: A008
- **Tags**: MCP, local, file-access

#### T10: An external attacker

**Statement**: A An external attacker with network access to the Amazon CloudFront endpoint can open many concurrent WebSocket connections to exhaust Amazon ECS on AWS Fargate container memory (in-memory session store) or trigger excessive Amazon Bedrock API calls, causing resource exhaustion or cost escalation, which leads to service unavailability for legitimate users, excessive AWS costs from Amazon Bedrock API abuse, or container OOM crashes

- **Prerequisites**: with network access to the Amazon CloudFront endpoint
- **Action**: open many concurrent WebSocket connections to exhaust Amazon ECS on AWS Fargate container memory (in-memory session store) or trigger excessive Amazon Bedrock API calls, causing resource exhaustion or cost escalation
- **Impact**: service unavailability for legitimate users, excessive AWS costs from Amazon Bedrock API abuse, or container OOM crashes
- **Tags**: DoS, WebSocket, resource-exhaustion

#### T11: A malicious authenticated user

**Statement**: A A malicious authenticated user with valid authentication credentials can access codebases and conversation histories belonging to other users since no role-based access control or resource-level authorization exists, which leads to unauthorized access to other users' proprietary source code and conversation data, violating data isolation in multi-tenant deployments

- **Prerequisites**: with valid authentication credentials
- **Action**: access codebases and conversation histories belonging to other users since no role-based access control or resource-level authorization exists
- **Impact**: unauthorized access to other users' proprietary source code and conversation data, violating data isolation in multi-tenant deployments
- **Impacted Assets**: A008, A010
- **Tags**: authorization, RBAC, multi-tenant

#### T12: An insider with Amazon DynamoDB read access

**Statement**: A An insider with Amazon DynamoDB read access when Amazon DynamoDB conversation logging is enabled without CMK encryption can access conversation history stored in Amazon DynamoDB which may contain sensitive code snippets, proprietary logic, or security-relevant information discussed in chat, which leads to exposure of sensitive conversation data including code snippets, architectural details, and security discussions

- **Prerequisites**: when Amazon DynamoDB conversation logging is enabled without CMK encryption
- **Action**: access conversation history stored in Amazon DynamoDB which may contain sensitive code snippets, proprietary logic, or security-relevant information discussed in chat
- **Impact**: exposure of sensitive conversation data including code snippets, architectural details, and security discussions
- **Impacted Assets**: A010
- **Tags**: DynamoDB, encryption, conversation-history

#### T13: A supply chain attacker

**Statement**: A A supply chain attacker when third-party Python packages are installed in the Docker image can compromise a third-party dependency (e.g., via typosquatting or package takeover) to inject malicious code into the container, gaining access to customer data and AWS credentials, which leads to full compromise of the application container, access to customer source code, IAM credentials, and ability to exfiltrate data

- **Prerequisites**: when third-party Python packages are installed in the Docker image
- **Action**: compromise a third-party dependency (e.g., via typosquatting or package takeover) to inject malicious code into the container, gaining access to customer data and AWS credentials
- **Impact**: full compromise of the application container, access to customer source code, IAM credentials, and ability to exfiltrate data
- **Tags**: supply-chain, dependency, container

## Mitigations

### Identified Mitigations

#### M1: Enforce Amazon Cognito configuration as mandatory in production deployments. Add startup validation that fails fast if USER_POOL_ID and USER_POOL_CLIENT_ID are not set. Remove the anonymous fallback behavior.

**Addresses Threats**: T1

#### M2: Implement prompt injection detection and prevention. Add input sanitization for user queries before sending to Amazon Bedrock. Use system prompt hardening techniques and output validation to prevent LLM manipulation.

**Addresses Threats**: T2

#### M3: Implement role-based access control (RBAC) to restrict user access to specific codebases. Add resource-level authorization checks that validate user permissions before granting access to codebase data.

**Addresses Threats**: T11

#### M4: Implement WebSocket connection rate limiting and per-user session limits. Add Amazon Bedrock API call budgets and throttling to prevent cost escalation from abuse.

**Addresses Threats**: T10

#### M5: Tighten Content Security Policy by removing unsafe-inline and unsafe-eval directives. Use nonce-based CSP for inline scripts. Implement output encoding for all AI-generated content rendered in the frontend.

**Addresses Threats**: T5

#### M6: Enable Customer Managed Keys (CMK) for Amazon DynamoDB encryption when conversation logging is enabled. Implement data retention policies and automatic purging of old conversation data.

**Addresses Threats**: T12

#### M7: Implement Amazon S3 bucket policy best practices: block public access, enforce encryption, restrict access to specific IAM roles, enable versioning and access logging. Use VPC endpoint policies to restrict Amazon S3 access.

**Addresses Threats**: T3

#### M8: Implement dependency scanning in CI/CD pipeline. Pin dependency versions. Use private package registry. Regularly audit and update dependencies for known vulnerabilities.

**Addresses Threats**: T13

#### M9: Implement short-lived JWT tokens with automatic refresh. Add token binding to prevent replay attacks. Consider implementing WebSocket-level session tokens that are distinct from authentication tokens.

**Addresses Threats**: T6

#### M10: Apply least-privilege IAM policies for Amazon ECS task roles. Separate read and write permissions. Use condition keys to restrict access to specific resources. Enable IMDSv2 to protect container metadata.

**Addresses Threats**: T7

## Assumptions

### A001: Authentication

**Description**: Amazon Cognito is properly configured in production deployments with self-signup disabled

- **Impact**: If Amazon Cognito is not configured, the system falls back to anonymous access, exposing all features to unauthenticated users
- **Rationale**: The code shows authentication is optional - when USER_POOL_ID and USER_POOL_CLIENT_ID are not set, auth is disabled and anonymous access is granted

### A002: Network

**Description**: VPC endpoints are configured for all AWS service access (Amazon S3, Amazon Bedrock, Amazon CloudWatch, Amazon ECR)

- **Impact**: Without VPC endpoints, traffic to AWS services traverses the public internet via NAT Gateway, increasing exposure
- **Rationale**: Architecture documentation specifies VPC endpoints but CDK deployment may not enforce them

### A003: AWS Services

**Description**: Amazon Bedrock does not retain or use customer prompts for model training

- **Impact**: If Amazon Bedrock retained prompts, customer source code sent in prompts could be exposed
- **Rationale**: Amazon Bedrock documentation states that customer data is not used for training, but this is an external dependency

### A004: Authentication

**Description**: No role-based access control (RBAC) exists - all authenticated users have equal access to all features and codebases

- **Impact**: Any authenticated user can access any codebase loaded into the system, creating risk of unauthorized data access in multi-tenant scenarios
- **Rationale**: Code review shows no authorization checks beyond authentication. Session isolation is per-connection, not per-user-permission.

## Phase Progress

| Phase | Name                                | Completion |
| ----- | ----------------------------------- | ---------- |
| 1     | Business Context Analysis           | 100% ✅    |
| 2     | Architecture Analysis               | 100% ✅    |
| 3     | Threat Actor Analysis               | 100% ✅    |
| 4     | Trust Boundary Analysis             | 100% ✅    |
| 5     | Asset Flow Analysis                 | 100% ✅    |
| 6     | Threat Identification               | 100% ✅    |
| 7     | Mitigation Planning                 | 100% ✅    |
| 7.5   | Code Validation Analysis            | 100% ✅    |
| 8     | Residual Risk Analysis              | 100% ✅    |
| 9     | Output Generation and Documentation | 100% ✅    |

## Residual Risk Summary (POC Release)

The following risks are accepted for the POC release and should be addressed before any production deployment:

| Risk                                         | Severity | Rationale                                                                                      |
| -------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------- |
| T1 — Anonymous access in local/dev mode      | Low      | By design for developer experience; CDK deployment always enforces Cognito                     |
| T8 — Log injection                           | Medium   | `sanitize_for_log` provides partial coverage; full structured logging deferred                 |
| T11 — No RBAC / multi-tenant isolation       | High     | POC assumes single-tenant (one codebase per deployment); RBAC required before multi-tenant use |
| T12 — Conversation history plaintext at rest | Medium   | File permissions restricted to owner; encryption-at-rest deferred for POC                      |

All high/critical threats (T2, T5, T6, T7, T9, T10, T13) have been mitigated or significantly reduced prior to open-source release.

---

_This threat model was initially generated by the Threat Modeling MCP Server and updated manually to reflect security hardening completed for open-source release (2026-04-29)._
