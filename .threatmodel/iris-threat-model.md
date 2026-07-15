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

IRIS is a cloud-native AI-powered code analysis and chat application built on AWS. It allows users to upload codebases to Amazon S3, generates summaries and context using Amazon Bedrock LLMs (Claude models), and provides a chat interface for querying code. The system uses a React frontend served via Amazon CloudFront from a private Amazon S3 bucket, an Amazon Bedrock AgentCore Runtime backend, Amazon Cognito for authentication, and Amazon S3 for codebase storage. It also exposes an MCP server for IDE integration.

### Key Statistics

- **Total Threats**: 11
- **Total Mitigations**: 9
- **Total Assumptions**: 4
- **System Components**: 8
- **Assets**: 13
- **Threat Actors**: 13

### Threat-to-Mitigation Summary

| #   | Threat                                                         | Severity | Mitigation                                                                                                                                                   |
| --- | -------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| T1  | Auth bypass when Cognito is not configured (local/Docker only) | Low      | Managed Cognito JWT authorizer is enforced in cloud deployments; only affects local dev. **POC accepted risk.**                                              |
| T2  | Prompt injection via agentic framework                         | Critical | ✅ Partially mitigated: Amazon Bedrock Guardrails + trust markers wrapping untrusted file content in system prompts + file allowlist filtering                |
| T3  | Direct S3 bucket access via misconfigured policies             | Critical | Block public access, read-only scoped execution role, `enforce_ssl`                                                                                          |
| T4  | XSS via unsafe-inline/unsafe-eval CSP                          | High     | ✅ Fixed: removed `rehype-raw`, DOMPurify sanitization added                                                                                                  |
| T5  | JWT token replay / session impersonation                       | High     | ✅ Mitigated: managed Cognito authorizer validates issuer/signature/expiry on every invocation; short-lived access tokens                                     |
| T6  | AgentCore execution-role abuse via agent-code compromise       | High     | ✅ Fixed: Amazon Bedrock IAM scoped to inference profiles + foundation model ARNs; guardrail permission scoped to a specific ARN; managed microVM isolation   |
| T7  | Log injection / repudiation                                    | Medium   | Partially mitigated by existing `sanitize_for_log`. **POC accepted risk.**                                                                                   |
| T8  | MCP server path traversal                                      | Medium   | ✅ Fixed: path containment check (`resolve().relative_to()`) in `read_multiple_files`; MCP command allowlist (deferred)                                       |
| T9  | Invocation flooding / Amazon Bedrock cost escalation           | High     | Per-session microVM isolation + managed authorizer gate access; Amazon Bedrock quotas + cost budgets. No app-level rate limiter — WAF rate rules recommended. |
| T10 | Missing RBAC / cross-tenant access                             | High     | **POC accepted risk** — single-tenant deployment assumed. Multi-tenant RBAC deferred.                                                                        |
| T11 | Supply chain dependency compromise                             | High     | pip-audit in CI/CD, pinned deps with hashes, Dependabot                                                                                                       |

## Business Context

**Description**: IRIS is a cloud-native AI-powered code analysis and chat application built on AWS. It allows users to upload codebases to Amazon S3, generates summaries and context using Amazon Bedrock LLMs (Claude models), and provides a chat interface for querying code. The system uses a React frontend served via Amazon CloudFront from a private Amazon S3 bucket, an Amazon Bedrock AgentCore Runtime backend, Amazon Cognito for authentication, and Amazon S3 for codebase storage. It also exposes an MCP server for IDE integration.

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

| ID   | Name                             | Type     | Service Provider | Description                                                                                                                                                                                                                                             |
| ---- | -------------------------------- | -------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C001 | React Frontend                   | Compute  | AWS              | React (Vite) SPA served as static assets from a private Amazon S3 bucket via Amazon CloudFront (Origin Access Control). Handles client-side routing and state; invokes the AgentCore Runtime data-plane endpoint directly over HTTPS with SSE responses. |
| C002 | Amazon CloudFront                | Network  | AWS              | CDN delivering the static React app from the private Amazon S3 origin via Origin Access Control. Enforces HTTPS (REDIRECT_TO_HTTPS), TLS 1.2 (2021 policy), the managed `SECURITY_HEADERS` response-headers policy, and SPA routing (403/404 → /index.html). |
| C003 | Amazon Bedrock AgentCore Runtime | Compute  | AWS              | Serverless managed runtime hosting the IRIS agent (`backend/agent_runtime.py`; HTTP protocol: `POST /invocations` with SSE + `GET /ping`). Each `runtimeSessionId` runs in an isolated microVM (ARM64, non-root). A built-in Amazon Cognito JWT authorizer validates the bearer token before requests reach the container. `networkMode` PUBLIC. |
| C004 | Amazon Bedrock                   | Compute  | AWS              | Amazon Bedrock LLM service providing Claude (Haiku and Sonnet) inference. Used for code analysis, summarization, and agentic chat. Supports prompt caching and streaming responses. Accessed via the AgentCore execution role.                          |
| C005 | Amazon S3 Codebase Bucket        | Storage  | AWS              | External, customer-owned Amazon S3 bucket storing codebase artifacts and analysis outputs. SSE-S3 encryption enforced, optional CMK. Accessed read-only by the AgentCore execution role.                                                               |
| C006 | Amazon Cognito                   | Security | AWS              | Amazon Cognito User Pool + User Pool Client providing JWT-based authentication (RS256). Issues access and ID tokens; the frontend sends the access token. The AgentCore Runtime authorizer validates tokens against the pool's OIDC discovery URL (`allowedClients` = app client id). Self-signup disabled by default. |
| C007 | Amazon CloudWatch Logs           | Other    | AWS              | Amazon CloudWatch Logs for Runtime application events and errors (`/aws/bedrock-agentcore/runtimes/*`), plus Amazon CloudFront access logs and Amazon S3 server access logs stored in Amazon S3, and AWS X-Ray traces. Default 7-day retention, configurable. |
| C008 | MCP Server                       | Compute  | Other            | Local MCP server exposing codebase_context and codebase_query tools for IDE integration. Runs as a local process, communicates via stdio. Provides path validation and configurable tool enablement.                                                    |

### Connections

| ID    | Source | Destination | Protocol | Port | Encrypted | Description                                                                                                              |
| ----- | ------ | ----------- | -------- | ---- | --------- | ------------------------------------------------------------------------------------------------------------------------ |
| CN001 | C001   | C002        | HTTPS    | 443  | Yes       | Users load the React app from Amazon CloudFront over HTTPS with TLS 1.2+                                                 |
| CN002 | C001   | C003        | HTTPS    | 443  | Yes       | Browser invokes the AgentCore Runtime data-plane endpoint directly (`POST /invocations`, SSE) with `Authorization: Bearer <Cognito access token>` |
| CN003 | C001   | C006        | HTTPS    | 443  | Yes       | Browser authenticates with Amazon Cognito (SRP) to obtain JWT tokens                                                    |
| CN004 | C003   | C006        | HTTPS    | 443  | Yes       | The Runtime's managed authorizer validates the bearer token against Amazon Cognito's OIDC discovery / JWKS endpoint      |
| CN005 | C003   | C004        | HTTPS    | 443  | Yes       | Agent invokes Amazon Bedrock models for code analysis, summarization, and chat                                          |
| CN006 | C003   | C005        | HTTPS    | 443  | Yes       | Agent reads codebase artifacts from the external customer Amazon S3 bucket (read-only)                                   |
| CN007 | C003   | C007        | HTTPS    | 443  | Yes       | Runtime emits application logs and traces to Amazon CloudWatch / AWS X-Ray                                               |

### Data Stores

| ID   | Name                    | Type           | Classification | Encrypted at Rest | Description                                                                                                                                                     |
| ---- | ----------------------- | -------------- | -------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D001 | S3 Codebase Artifacts   | Object Storage | Confidential   | Yes               | External customer-owned Amazon S3 bucket storing uploaded codebases, analysis artifacts, and codebase representations. SSE-S3 enforced, optional CMK.           |
| D002 | In-Session Runtime State | Other          | Internal       | N/A               | Per-`runtimeSessionId` state (active agent instance, user info, conversation state) held in the isolated microVM's memory/filesystem. Ephemeral; sanitized on session termination. Not persisted to any datastore. |
| D003 | Local File Cache        | Other          | Internal       | No                | Local file cache (.iris_cache/) storing file hashes and codebase overview data for performance optimization. Deleted files cleaned automatically.               |

> **Note**: No persistent conversation store is deployed. The stack provisions no Amazon DynamoDB table and no AgentCore Memory resource; a DynamoDB logger and a Memory hook exist in the codebase but are not wired into the deployed stack.

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
- **Description**: External attacker targeting the Amazon CloudFront distribution or the AgentCore Runtime data-plane endpoint to gain unauthorized access or disrupt service.

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
- **Description**: Public internet where end users access the application via the Amazon CloudFront HTTPS endpoint and invoke the AgentCore Runtime data-plane endpoint

#### Edge Layer

- **Trust Level**: TrustLevel.MEDIUM
- **Description**: Amazon CloudFront edge layer serving the static React app from a private Amazon S3 origin via Origin Access Control

#### AWS Managed Services

- **Trust Level**: TrustLevel.HIGH
- **Description**: AWS managed services accessed via the AgentCore execution role and the managed authorizer: Amazon Bedrock, Amazon S3, Amazon CloudWatch, Amazon Cognito

#### Local Developer Environment

- **Trust Level**: TrustLevel.MEDIUM
- **Description**: Local developer machine running MCP server for IDE integration. Communicates via stdio, no network exposure.

#### Managed Runtime (AgentCore)

- **Trust Level**: TrustLevel.HIGH
- **Description**: Amazon Bedrock AgentCore Runtime microVMs hosting the agent. Fully managed by AWS; each session is isolated in its own microVM. No customer-managed VPC or network layer.

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
- **Controls**: HTTPS enforcement, TLS 1.2+, managed security headers
- **Description**: Boundary between the public internet and the Amazon CloudFront edge layer. All traffic must be HTTPS. (A Web Application Firewall is out of scope for this proof-of-value; access to the backend is gated by the Cognito authorizer at the Runtime layer.)

#### Runtime Authorization Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Managed Amazon Cognito JWT authorizer, TLS 1.2+
- **Description**: Boundary between the public AgentCore data-plane endpoint and the agent microVM. The managed authorizer validates the Cognito bearer token (issuer, RS256 signature, expiry, `allowedClients` against `client_id`) before any request reaches the container.

#### Runtime to AWS Services Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: AgentCore execution role, TLS 1.2+, least-privilege policies
- **Description**: Boundary between the agent microVM and AWS managed services. All access is via the scoped AgentCore execution role over TLS.

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
| A012 | AgentCore Execution Role Credentials | AssetType.CREDENTIAL | AssetClassification.RESTRICTED | 5           | 5           | N/A   |
| A013 | Application Configuration         | AssetType.DATA       | AssetClassification.INTERNAL     | 3           | 2           | N/A   |

### Asset Flows

| ID   | Asset                             | Source | Destination | Protocol | Encrypted | Risk Level |
| ---- | --------------------------------- | ------ | ----------- | -------- | --------- | ---------- |
| F001 | User Credentials                  | C001   | C006        | HTTPS    | Yes       | 4          |
| F002 | JWT Authentication Tokens         | C006   | C001        | HTTPS    | Yes       | 3          |
| F003 | JWT Authentication Tokens         | C001   | C003        | HTTPS    | Yes       | 5          |
| F004 | LLM Prompts and Responses         | C003   | C004        | HTTPS    | Yes       | 4          |
| F005 | Customer Source Code              | C005   | C003        | HTTPS    | Yes       | 4          |
| F006 | Audit Logs                        | C003   | C007        | HTTPS    | Yes       | 2          |

## Threats

### Identified Threats

#### T1: An unauthenticated attacker (local/Docker only)

**Statement**: An unauthenticated attacker, when running the system locally or via Docker without Cognito environment variables configured, can access the system without authentication since the backend falls back to anonymous mode. In cloud (CDK) deployments, Amazon Cognito is always provisioned and the AgentCore Runtime enforces its Cognito JWT authorizer on every invocation, so this threat does not apply to production.

- **Prerequisites**: when running locally or via Docker without Cognito configuration (`ALLOW_ANONYMOUS` / `authEnabled === false`)
- **Action**: access the system without authentication since the backend falls back to anonymous mode, granting default claims (sub: anonymous)
- **Impact**: complete unauthenticated access to all system features including codebase analysis and chat capabilities (local/dev environment only)
- **Severity**: Low (production not affected — the cloud Runtime always enforces the Cognito authorizer)
- **Impacted Assets**: A009
- **Tags**: authentication, misconfiguration, bypass

#### T2: An authenticated user

**Statement**: An authenticated user with access to the chat interface can craft malicious prompts to manipulate the LLM agent into revealing system prompts, accessing unauthorized files via the file retrieval agent, or executing unintended tool calls through the agentic framework, which leads to unauthorized access to customer source code, exfiltration of system prompts, or unintended information disclosure via agent tool calls.

- **Prerequisites**: with authenticated access to the chat interface
- **Action**: craft malicious prompts to manipulate the LLM agent into revealing system prompts, accessing unauthorized files via the file retrieval agent, or executing unintended tool calls through the agentic framework
- **Impact**: unauthorized access to customer source code, exfiltration of system prompts, or unintended information disclosure via agent tool calls
- **Impacted Assets**: A008, A011
- **Tags**: prompt-injection, LLM, agentic

#### T3: An insider or external attacker

**Statement**: An insider or external attacker with access to the AWS account or misconfigured S3 bucket policies can access the S3 codebase artifacts bucket directly, bypassing application-level controls, due to overly permissive bucket policies or IAM permissions, which leads to direct access to all customer source code stored in the S3 bucket, bypassing all application security controls.

- **Prerequisites**: with access to the AWS account or misconfigured S3 bucket policies
- **Action**: access the S3 codebase artifacts bucket directly, bypassing application-level controls, due to overly permissive bucket policies or IAM permissions
- **Impact**: direct access to all customer source code stored in the S3 bucket, bypassing all application security controls
- **Impacted Assets**: A008
- **Tags**: S3, data-exposure, misconfiguration

#### T4: An attacker

**Statement**: An attacker with the ability to exploit unsafe-inline and unsafe-eval CSP directives in the frontend can inject malicious JavaScript via the chat interface that executes in other users' browsers, leveraging the CSP's unsafe-inline and unsafe-eval directives, which leads to theft of JWT tokens, session hijacking, or manipulation of the chat interface to display misleading AI responses.

- **Prerequisites**: with ability to exploit unsafe-inline and unsafe-eval CSP directives in the frontend
- **Action**: inject malicious JavaScript via the chat interface that executes in other users' browsers, leveraging the CSP's unsafe-inline and unsafe-eval directives
- **Impact**: theft of JWT tokens, session hijacking, or manipulation of the chat interface to display misleading AI responses
- **Tags**: XSS, CSP, frontend

#### T5: An external attacker

**Statement**: An external attacker with access to a stolen or leaked JWT token can replay the token to invoke the AgentCore Runtime and impersonate the legitimate user's session, which leads to full access to the impersonated user's session, including their codebase analysis results and conversation history.

- **Prerequisites**: with access to a stolen or leaked JWT token
- **Action**: replay the token to invoke the AgentCore Runtime and impersonate the legitimate user's session
- **Impact**: full access to the impersonated user's session, including their codebase analysis results and conversation history
- **Impacted Assets**: A009
- **Tags**: session-hijacking, JWT, token-replay

#### T6: An attacker

**Statement**: An attacker with code execution inside the agent container (e.g., via a supply chain attack) can access the Amazon Bedrock AgentCore Runtime execution role credentials to gain access to Amazon Bedrock, Amazon S3, and AWS KMS, which leads to full access to all AWS services the execution role can access, including customer source code in Amazon S3 and Amazon Bedrock model invocation.

- **Prerequisites**: with code execution inside the agent container (e.g., via a supply chain attack). The AgentCore microVM is managed and isolated (no customer-managed instance metadata service), which removes the EC2/ECS IMDS credential-theft vector; however, the scoped execution-role credentials remain a concern on code compromise.
- **Action**: access the AgentCore Runtime execution role credentials to gain access to Amazon Bedrock, Amazon S3, and AWS KMS
- **Impact**: full access to all AWS services the execution role can access, including customer source code in Amazon S3 and Amazon Bedrock model invocation
- **Impacted Assets**: A012
- **Tags**: IAM, credential-theft, agent-runtime

#### T7: A malicious user

**Statement**: A malicious user with authenticated access to the system can inject crafted input to create misleading log entries or deny performing actions when audit trails are insufficient, which leads to inability to attribute malicious actions to specific users, corrupted audit trails, or false log entries that mislead incident response.

- **Prerequisites**: with authenticated access to the system
- **Action**: inject crafted input to create misleading log entries or deny performing actions when audit trails are insufficient
- **Impact**: inability to attribute malicious actions to specific users, corrupted audit trails, or false log entries that mislead incident response
- **Tags**: logging, log-injection, audit

#### T8: A malicious IDE plugin or compromised MCP client

**Statement**: A malicious IDE plugin or compromised MCP client with access to the local developer machine running the MCP server can exploit the MCP server's codebase_context or codebase_query tools to access files outside the intended codebase directory via path traversal, which leads to access to sensitive files on the developer's machine beyond the intended codebase scope.

- **Prerequisites**: with access to the local developer machine running the MCP server
- **Action**: exploit the MCP server's codebase_context or codebase_query tools to access files outside the intended codebase directory via path traversal
- **Impact**: access to sensitive files on the developer's machine beyond the intended codebase scope
- **Impacted Assets**: A008
- **Tags**: MCP, local, file-access

#### T9: An external attacker

**Statement**: An external attacker with authenticated access to the AgentCore Runtime endpoint can open many concurrent sessions or send high-volume invocations to trigger excessive Amazon Bedrock API calls, causing cost escalation, which leads to excessive AWS costs from Amazon Bedrock API abuse, or throttling that degrades service for legitimate users.

- **Prerequisites**: with authenticated access to the AgentCore Runtime endpoint
- **Action**: open many concurrent sessions or send high-volume invocations to trigger excessive Amazon Bedrock API calls, causing cost escalation
- **Impact**: excessive AWS costs from Amazon Bedrock API abuse, or throttling that degrades service for legitimate users
- **Tags**: DoS, cost, resource-exhaustion

#### T10: A malicious authenticated user

**Statement**: A malicious authenticated user with valid authentication credentials can access codebases and conversation histories belonging to other users since no role-based access control or resource-level authorization exists, which leads to unauthorized access to other users' proprietary source code and conversation data, violating data isolation in multi-tenant deployments.

- **Prerequisites**: with valid authentication credentials
- **Action**: access codebases and conversation histories belonging to other users since no role-based access control or resource-level authorization exists
- **Impact**: unauthorized access to other users' proprietary source code and conversation data, violating data isolation in multi-tenant deployments
- **Impacted Assets**: A008, A010
- **Tags**: authorization, RBAC, multi-tenant

#### T11: A supply chain attacker

**Statement**: A supply chain attacker, when third-party Python packages are installed in the container image, can compromise a third-party dependency (e.g., via typosquatting or package takeover) to inject malicious code into the container, gaining access to customer data and AWS credentials, which leads to full compromise of the agent container, access to customer source code, IAM credentials, and the ability to exfiltrate data.

- **Prerequisites**: when third-party Python packages are installed in the container image
- **Action**: compromise a third-party dependency (e.g., via typosquatting or package takeover) to inject malicious code into the container, gaining access to customer data and AWS credentials
- **Impact**: full compromise of the agent container, access to customer source code, IAM credentials, and ability to exfiltrate data
- **Tags**: supply-chain, dependency, container

## Mitigations

### Identified Mitigations

#### M1: Enforce Amazon Cognito configuration as mandatory in production deployments. The cloud Runtime always enforces its managed Cognito authorizer; the anonymous fallback exists only for local development.

**Addresses Threats**: T1

#### M2: Implement prompt injection detection and prevention. Add input sanitization for user queries before sending to Amazon Bedrock. Use system prompt hardening techniques (wrapping untrusted file content in explicit markers) and output validation to prevent LLM manipulation.

**Addresses Threats**: T2

#### M3: Implement role-based access control (RBAC) to restrict user access to specific codebases. Add resource-level authorization checks that validate user permissions before granting access to codebase data.

**Addresses Threats**: T10

#### M4: Implement per-session invocation rate limiting and per-user session limits. Add Amazon Bedrock API call budgets and throttling to prevent cost escalation from abuse. Consider WAF rate-based rules and Amazon Bedrock quota/budget alarms.

**Addresses Threats**: T9

#### M5: Tighten Content Security Policy by removing unsafe-inline and unsafe-eval directives. Use nonce-based CSP for inline scripts. Implement output encoding for all AI-generated content rendered in the frontend.

**Addresses Threats**: T4

#### M6: Implement Amazon S3 bucket policy best practices: block public access, enforce encryption, restrict access to specific IAM roles (read-only for the codebase bucket), enable versioning and access logging.

**Addresses Threats**: T3

#### M7: Implement dependency scanning in CI/CD pipeline. Pin dependency versions. Use private package registry. Regularly audit and update dependencies for known vulnerabilities.

**Addresses Threats**: T11

#### M8: Implement short-lived JWT access tokens with automatic refresh. Add token binding to prevent replay attacks. The managed Cognito authorizer validates issuer, signature, and expiry on every invocation.

**Addresses Threats**: T5

#### M9: Apply least-privilege IAM policies to the Amazon Bedrock AgentCore Runtime execution role. Separate read and write permissions. Use condition keys to restrict access to specific resources.

**Addresses Threats**: T6

## Assumptions

### A001: Authentication

**Description**: Amazon Cognito is properly configured in production deployments with self-signup disabled

- **Impact**: If Amazon Cognito is not configured, local/dev deployments fall back to anonymous access; the cloud Runtime always enforces the managed authorizer
- **Rationale**: The code shows authentication is optional for local runs — when Cognito is not configured, `ALLOW_ANONYMOUS` / `authEnabled === false` grants anonymous access. Cloud deployments provision Cognito and the Runtime authorizer.

### A002: Network

**Description**: The Amazon Bedrock AgentCore Runtime isolates each session in a dedicated microVM and manages network access to AWS services (Amazon S3, Amazon Bedrock, Amazon CloudWatch) on behalf of the agent

- **Impact**: The customer does not provision or manage a VPC, subnets, NAT gateways, or VPC endpoints; network isolation and egress are managed by the serverless Runtime
- **Rationale**: `networkMode` is PUBLIC and the Runtime is fully managed; there is no customer-managed network layer to configure

### A003: AWS Services

**Description**: Amazon Bedrock does not retain or use customer prompts for model training

- **Impact**: If Amazon Bedrock retained prompts, customer source code sent in prompts could be exposed
- **Rationale**: Amazon Bedrock documentation states that customer data is not used for training, but this is an external dependency

### A004: Authentication

**Description**: No role-based access control (RBAC) exists - all authenticated users have equal access to all features and codebases

- **Impact**: Any authenticated user can access any codebase loaded into the system, creating risk of unauthorized data access in multi-tenant scenarios
- **Rationale**: Code review shows no authorization checks beyond authentication. Session isolation is per-session, not per-user-permission.

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
| T1 — Anonymous access in local/dev mode      | Low      | By design for developer experience; the cloud Runtime always enforces the Cognito authorizer   |
| T7 — Log injection                           | Medium   | `sanitize_for_log` provides partial coverage; full structured logging deferred                 |
| T9 — Invocation flooding / Bedrock cost      | High     | No app-level rate limiter in the serverless model; WAF rate rules + Bedrock quota/budget alarms recommended |
| T10 — No RBAC / multi-tenant isolation       | High     | POC assumes single-tenant (one codebase per deployment); RBAC required before multi-tenant use |

All high/critical threats (T2, T3, T4, T5, T6, T8, T11) have been mitigated or significantly reduced prior to open-source release.

---

_This threat model was initially generated by the Threat Modeling MCP Server and updated manually to reflect security hardening completed for open-source release (2026-04-29)._
