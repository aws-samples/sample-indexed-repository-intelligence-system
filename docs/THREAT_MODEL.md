# Threat Model — IRIS

<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

**Version**: 1.1
**Date**: 2026-05-06
**Methodology**: STRIDE
**Status**: POC Release — residual risks documented and accepted

> **POC Notice**: This project is a proof-of-concept demonstration. Several threats below are accepted risks at this stage and documented for awareness. This threat model reflects the current state of the codebase and the mitigations implemented prior to open-source release.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Security and Trust Boundaries](#2-security-and-trust-boundaries)
3. [Data Flows](#3-data-flows)
4. [STRIDE Threat Analysis](#4-stride-threat-analysis)
5. [Identified Threats and Mitigations](#5-identified-threats-and-mitigations)
6. [Residual Risks and Accepted Risks](#6-residual-risks-and-accepted-risks)
7. [Assumptions](#7-assumptions)

---

## 1. System Overview

IRIS is a cloud-native AI-powered code analysis and chat application built on AWS. Users upload codebases to Amazon S3; the system generates summaries and context using Amazon Bedrock (Claude models) and provides a real-time WebSocket-based chat interface for querying code.

### Components

| ID   | Component                   | Technology                | Hosting                                     |
| ---- | --------------------------- | ------------------------- | ------------------------------------------- |
| C001 | React Frontend              | React 18+ / TypeScript    | Amazon CloudFront + S3                      |
| C002 | Application Load Balancer   | AWS ALB                   | Public subnets (VPC)                        |
| C003 | FastAPI WebSocket Server    | Python / FastAPI          | Amazon ECS on AWS Fargate (private subnets) |
| C004 | Amazon Bedrock              | Claude 3.5 Haiku / Sonnet | AWS Managed                                 |
| C005 | S3 Codebase Bucket          | Amazon S3                 | AWS Managed                                 |
| C006 | DynamoDB Conversation Store | Amazon DynamoDB           | AWS Managed (optional)                      |
| C007 | VPC Network                 | Amazon VPC (10.0.0.0/16)  | AWS Managed                                 |
| C008 | Amazon Cognito              | Cognito User Pool         | AWS Managed                                 |
| C009 | Amazon CloudWatch Logs      | CloudWatch                | AWS Managed                                 |
| C010 | MCP Server                  | Python / stdio            | Local developer machine                     |
| C011 | BedrockAgentCore Memory     | Amazon Bedrock AgentCore  | AWS Managed (optional)                      |

---

## 2. Security and Trust Boundaries

### Trust Zones

```
┌─────────────────────────────────────────────────────────────────────┐
│  UNTRUSTED — Public Internet                                        │
│  End users, browsers, IDE clients                                   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  DMZ / Edge Layer (MEDIUM trust)                              │  │
│  │  CloudFront CDN  ←→  Application Load Balancer               │  │
│  │                                                               │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  Application Layer — Private VPC (HIGH trust)           │  │  │
│  │  │  ECS Fargate (FastAPI WebSocket Server)                 │  │  │
│  │  │                                                         │  │  │
│  │  │  ┌───────────────────────────────────────────────────┐  │  │  │
│  │  │  │  AWS Managed Services (HIGH trust)                │  │  │  │
│  │  │  │  Bedrock · S3 · DynamoDB · Cognito · CloudWatch   │  │  │  │
│  │  │  │  BedrockAgentCore Memory (optional)               │  │  │  │
│  │  │  └───────────────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  LOCAL DEVELOPER ENVIRONMENT (MEDIUM trust, separate boundary)      │
│  MCP Server (stdio) — no network exposure                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Boundary Definitions

| Boundary                   | Type     | Controls                                                          |
| -------------------------- | -------- | ----------------------------------------------------------------- |
| Internet → Edge            | Network  | CloudFront WAF, HTTPS/TLS 1.2+, security headers                  |
| Edge → Application         | Network  | Security groups (ALB-only ingress), private subnets               |
| Application → AWS Services | Network  | VPC endpoints, IAM task roles, TLS 1.2+, least-privilege policies |
| Browser → Backend          | Protocol | JWT (RS256) via Amazon Cognito, WebSocket over WSS                |
| Backend → AI Services      | Protocol | IAM task role, scoped to specific Bedrock model ARNs              |
| Backend → AgentCore Memory | Protocol | IAM task role, HTTPS via VPC endpoint (optional feature)          |
| Local → MCP Server         | Process  | stdio only; path containment enforced in three layers             |

---

## 3. Data Flows

### DF1 — User Authentication

```
Browser → CloudFront (HTTPS) → ALB (HTTP, AWS-internal) → ECS
       → Cognito JWKS endpoint (HTTPS) → JWT claims returned to ECS
```

**Data in transit**: Cognito JWT (RS256), user credentials
**Encrypted**: Yes (HTTPS end-to-end; ALB→ECS leg uses AWS Nitro System physical encryption)

### DF2 — WebSocket Chat Session

```
Browser → CloudFront (WSS) → ALB (WS, AWS-internal) → ECS
       → Bedrock (HTTPS via VPC endpoint) → streaming response
       → ECS → ALB → CloudFront → Browser
```

**Data in transit**: User queries (may contain code context), LLM responses
**Encrypted**: Yes

### DF3 — Codebase Upload and Analysis

```
S3 Bucket → ECS (HTTPS via VPC endpoint)
          → Bedrock (HTTPS via VPC endpoint) [summarization]
          → S3 (HTTPS via VPC endpoint) [artifacts written back]
```

**Data in transit**: Customer source code, analysis artifacts
**Encrypted**: Yes; S3 SSE-S3 at rest (CMK optional)

### DF4 — Conversation Logging (optional)

```
ECS → DynamoDB (HTTPS via VPC endpoint) [async write, 90-day TTL]
```

**Data in transit**: Conversation messages (truncated at 8.5 KB per message)
**Encrypted**: Yes; DynamoDB AWS-owned keys by default (CMK optional)

### DF5 — MCP Server (local)

```
IDE Plugin → MCP Server (stdio) → local file system
```

**Data in transit**: File paths, codebase content
**Encrypted**: N/A (local process communication)

### DF6 — AgentCore Memory (optional)

```
ECS → BedrockAgentCore Memory API (HTTPS via VPC endpoint) [per-message write]
    → BedrockAgentCore Memory API (HTTPS via VPC endpoint) [session load on agent init]
```

**Data in transit**: Full conversation message content (role + text), truncated to 500 chars if >8.5 KB
**Encrypted**: Yes; managed by BedrockAgentCore service
**Note**: This is an optional feature enabled only when `MemoryHookProvider` is configured. When active, conversation content is stored in an external AWS-managed service outside the application's DynamoDB table.

---

## 4. STRIDE Threat Analysis

STRIDE categories applied to each trust boundary and component:

| STRIDE Category            | Description                                    |
| -------------------------- | ---------------------------------------------- |
| **S**poofing               | Impersonating a user, service, or component    |
| **T**ampering              | Modifying data in transit or at rest           |
| **R**epudiation            | Denying actions without sufficient audit trail |
| **I**nformation Disclosure | Exposing data to unauthorized parties          |
| **D**enial of Service      | Making the system unavailable                  |
| **E**levation of Privilege | Gaining unauthorized permissions               |

### STRIDE Matrix

| Component / Boundary          | S                         | T                   | R                  | I                           | D                     | E                     |
| ----------------------------- | ------------------------- | ------------------- | ------------------ | --------------------------- | --------------------- | --------------------- |
| Browser ↔ Backend (WebSocket) | T6 (JWT replay)           | —                   | T8 (log injection) | T5 (XSS)                    | T10 (DoS)             | T11 (no RBAC)         |
| Backend ↔ Bedrock             | T2 (prompt injection)     | —                   | —                  | T2 (data exfil)             | T10 (cost escalation) | T2 (agent tool abuse) |
| Backend ↔ S3                  | T3 (IAM misconfiguration) | —                   | —                  | T3 (direct bucket access)   | —                     | T7 (task role theft)  |
| CloudFront → ALB (HTTP)       | —                         | T4 (interception)   | —                  | T4 (token exposure)         | —                     | —                     |
| ECS Container                 | T7 (credential theft)     | —                   | —                  | T7 (IAM abuse)              | —                     | T7 (container escape) |
| MCP Server (local)            | —                         | T9 (path traversal) | —                  | T9 (file disclosure)        | —                     | T9 (scope escape)     |
| Cognito / Auth                | T1 (anon bypass)          | —                   | —                  | T6 (token replay)           | —                     | T1 (auth bypass)      |
| DynamoDB / AgentCore Memory   | —                         | —                   | T8                 | T12 (conversation exposure) | —                     | —                     |
| Supply Chain                  | T13 (dep compromise)      | T13                 | —                  | T13                         | —                     | T13                   |
| Debug Endpoints               | T14 (misconfiguration)    | —                   | —                  | T14 (session info leak)     | —                     | T14                   |

---

## 5. Identified Threats and Mitigations

### T1 — Authentication Bypass (Local/Docker Mode)

| Field               | Detail                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Spoofing, Elevation of Privilege                                                                  |
| **Severity**        | Low (production not affected)                                                                     |
| **Actor**           | Unauthenticated attacker                                                                          |
| **Precondition**    | `USER_POOL_ID` / `USER_POOL_CLIENT_ID` env vars not set (local or Docker without Cognito)         |
| **Attack**          | Backend falls back to `ALLOW_ANONYMOUS=true`, granting `sub: anonymous` claims to all connections |
| **Impact**          | Full unauthenticated access to all features in local/dev environments                             |
| **Affected Assets** | JWT tokens (A009)                                                                                 |

**Mitigation**: CDK deployment always provisions Cognito and injects env vars into the ECS task — this path cannot be reached in cloud deployments. `ALLOW_ANONYMOUS` is explicitly documented as a dev-only flag with a warning log. **POC accepted risk** for local development.

---

### T2 — Prompt Injection via Agentic Framework

| Field               | Detail                                                                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Tampering, Information Disclosure, Elevation of Privilege                                                                                                             |
| **Severity**        | Critical                                                                                                                                                              |
| **Actor**           | Authenticated user                                                                                                                                                    |
| **Precondition**    | Authenticated WebSocket access                                                                                                                                        |
| **Attack**          | Crafted prompts manipulate the LLM agent into revealing system prompts, accessing unauthorized files via the file retrieval agent, or executing unintended tool calls |
| **Impact**          | Unauthorized access to customer source code, system prompt exfiltration, unintended tool execution                                                                    |
| **Affected Assets** | Customer source code (A008), LLM prompts/responses (A011)                                                                                                             |

**Mitigations implemented**:

- Amazon Bedrock Guardrails support is wired through `create_bedrock_agent()` and applied to model invocations when configured. Configuration is **opt-in**: the operator creates a Guardrail in the AWS Bedrock console (or via CDK) and sets `guardrail_id` in `infra/config.yaml`. When `guardrail_id` is set, `infra/stack.py` grants the ECS task role `bedrock:ApplyGuardrail` scoped to that ARN. Deployments without `guardrail_id` are unprotected at this layer — operators MUST configure a Guardrail before exposing the service to untrusted users.
- Trust-hierarchy markers (`[BEGIN UNTRUSTED FILE DATA]` / `[END UNTRUSTED FILE DATA]`) wrap all user-supplied file content in system prompts
- File retrieval agent uses an allowlist-based file filter; path containment enforced before any file is read (see T9)
- System prompt hardening with explicit instructions not to reveal internal prompts

**Residual risk**: Prompt injection is an unsolved problem in LLM security. Guardrails and markers reduce but do not eliminate risk.

---

### T3 — Direct S3 Bucket Access via Misconfigured Policies

| Field               | Detail                                                       |
| ------------------- | ------------------------------------------------------------ |
| **STRIDE**          | Spoofing, Information Disclosure                             |
| **Severity**        | Critical                                                     |
| **Actor**           | Insider or external attacker with AWS account access         |
| **Precondition**    | Overly permissive S3 bucket policy or IAM permissions        |
| **Attack**          | Direct S3 API access bypasses all application-level controls |
| **Impact**          | Full access to all customer source code in S3                |
| **Affected Assets** | Customer source code (A008)                                  |

**Mitigations implemented**:

- S3 Block Public Access enforced
- Bucket access restricted to ECS task role only
- VPC endpoint policy restricts S3 access to traffic originating from the VPC
- SSE-S3 encryption at rest enforced

---

### T4 — HTTP Interception Between CloudFront and ALB

| Field               | Detail                                                                        |
| ------------------- | ----------------------------------------------------------------------------- |
| **STRIDE**          | Information Disclosure, Tampering                                             |
| **Severity**        | Medium                                                                        |
| **Actor**           | Attacker with access to AWS internal network                                  |
| **Precondition**    | Ability to intercept traffic on the CloudFront → ALB leg (HTTP, AWS-internal) |
| **Attack**          | Capture JWT tokens, user queries, or AI responses in transit                  |
| **Impact**          | Exposure of authentication tokens and sensitive code context                  |
| **Affected Assets** | JWT tokens (A009), LLM prompts/responses (A011)                               |

**Mitigation**: This leg relies on AWS Nitro System physical encryption of the hypervisor network. End-to-end TLS from browser to CloudFront and from ECS to all AWS services is enforced. The CloudFront → ALB HTTP pattern is standard within AWS. **Accepted risk** — adding an HTTPS listener on the ALB is a future hardening option.

---

### T5 — XSS via Frontend Content Rendering

| Field               | Detail                                                                        |
| ------------------- | ----------------------------------------------------------------------------- |
| **STRIDE**          | Tampering, Information Disclosure                                             |
| **Severity**        | High                                                                          |
| **Actor**           | Attacker who can inject content into AI responses                             |
| **Precondition**    | Unsafe CSP directives or unescaped AI-generated HTML rendered in the browser  |
| **Attack**          | Malicious JavaScript executes in other users' browsers via the chat interface |
| **Impact**          | JWT token theft, session hijacking, misleading AI response injection          |
| **Affected Assets** | JWT tokens (A009)                                                             |

**Mitigations implemented**:

- `rehype-raw` removed from the Markdown rendering pipeline (eliminates raw HTML passthrough)
- ReactMarkdown configured with `skipHtml={true}` in `MessageBubble.jsx` so raw HTML in AI responses is not rendered
- Mermaid diagrams initialized with `securityLevel: 'strict'` (no raw-HTML / `click` JavaScript handlers); rendered SVG is run through DOMPurify (SVG profile) before DOM insertion in `MermaidChart.jsx`
- Backend CSP header enforced on all HTTP responses: `default-src 'self'; script-src 'self'; frame-ancestors 'none'` — no `unsafe-inline` or `unsafe-eval`
- Additional headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`

---

### T6 — JWT Token Replay / Session Hijacking

| Field               | Detail                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------- |
| **STRIDE**          | Spoofing, Information Disclosure                                                            |
| **Severity**        | High                                                                                        |
| **Actor**           | External attacker with a stolen JWT                                                         |
| **Precondition**    | Attacker obtains a valid JWT (e.g., via network interception or XSS)                        |
| **Attack**          | Replay the JWT to establish a WebSocket session and impersonate the legitimate user         |
| **Impact**          | Full access to the impersonated user's session, codebase analysis, and conversation history |
| **Affected Assets** | JWT tokens (A009)                                                                           |

**Mitigations implemented**:

- JWKS TTL cache (5-minute proactive refresh) with monotonic clock to prevent stale key acceptance
- Unknown `kid` refresh throttled to once per minute to prevent DoS via crafted tokens
- Session TTL of 1 hour with idle eviction; maximum 100 concurrent sessions enforced by `SessionManager`
- Cognito tokens include `exp` claim; `verify_exp=True` enforced in `jwt.decode`
- `token_use` claim validated — only `access` or `id` tokens accepted

---

### T7 — ECS Task Role Credential Theft

| Field               | Detail                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **STRIDE**          | Elevation of Privilege, Information Disclosure                                                                                 |
| **Severity**        | Critical                                                                                                                       |
| **Actor**           | Attacker with code execution inside the ECS container                                                                          |
| **Precondition**    | Container escape or supply chain compromise (see T13)                                                                          |
| **Attack**          | Query the ECS container metadata endpoint to obtain task role credentials, then access Bedrock, S3, DynamoDB, and KMS directly |
| **Impact**          | Full access to all AWS services the task role can reach, including customer source code                                        |
| **Affected Assets** | IAM task role credentials (A012)                                                                                               |

**Mitigations implemented**:

- IAM task role scoped to specific Bedrock inference profile ARNs and foundation model ARNs (not `bedrock:*`)
- Bedrock Guardrail permission scoped to the specific Guardrail ARN
- S3 access restricted to the specific codebase bucket ARN
- DynamoDB access restricted to the specific table ARN
- Container runs as non-root user

---

### T8 — Log Injection / Repudiation

| Field               | Detail                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Repudiation, Tampering                                                                                  |
| **Severity**        | Medium                                                                                                  |
| **Actor**           | Authenticated malicious user                                                                            |
| **Precondition**    | Authenticated access to the system                                                                      |
| **Attack**          | Inject newlines or control characters into user input to forge log entries or obscure malicious actions |
| **Impact**          | Corrupted audit trail, false log entries, inability to attribute actions                                |
| **Affected Assets** | Audit logs (A007)                                                                                       |

**Mitigations implemented**:

- `sanitize_for_log()` in `backend/security_utils.py` strips newlines (`\n` → `[NEWLINE]`), carriage returns, control characters (ASCII 0–31), and ANSI escape codes before any user-controlled value is logged
- Truncates log values to 200 characters to prevent log flooding
- CloudWatch Logs provides tamper-evident, append-only log storage

**Residual risk**: Structured JSON logging (e.g., via `python-json-logger`) would provide stronger guarantees. **POC accepted risk** — deferred to post-POC hardening.

---

### T9 — MCP Server / File Agent Path Traversal

| Field               | Detail                                                                                       |
| ------------------- | -------------------------------------------------------------------------------------------- |
| **STRIDE**          | Information Disclosure, Elevation of Privilege                                               |
| **Severity**        | Medium                                                                                       |
| **Actor**           | Malicious IDE plugin, compromised MCP client, or crafted prompt via T2                       |
| **Precondition**    | Ability to supply an arbitrary file path to any file-reading function                        |
| **Attack**          | Supply a path like `../../etc/passwd` to read files outside the intended codebase directory  |
| **Impact**          | Access to sensitive files on the developer's machine (MCP) or on the ECS container (backend) |
| **Affected Assets** | Customer source code (A008), local credentials                                               |

**Mitigations implemented — three independent layers**:

1. **`iris_mcp/mcp_server.py` `validate_file_within_codebase()`**: `Path.resolve().relative_to(codebase_root)` — raises `ValueError` on escape; applied before any file read in the MCP server
2. **`iris/agents/utils.py` `read_multiple_files()`**: Same `resolve().relative_to()` check applied to every path in the file list before reading
3. **`iris/file_system/file_utils.py` `read_source()`**: Same containment check applied at the lowest-level file read function

MCP server communicates via stdio only — no network port exposed.

---

### T10 — WebSocket DoS / Bedrock Cost Escalation

| Field               | Detail                                                                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Denial of Service                                                                                                                        |
| **Severity**        | High                                                                                                                                     |
| **Actor**           | External attacker with CloudFront access                                                                                                 |
| **Precondition**    | Network access to the CloudFront endpoint                                                                                                |
| **Attack**          | Open many concurrent WebSocket connections or flood chat messages to exhaust ECS container memory or trigger excessive Bedrock API calls |
| **Impact**          | Service unavailability for legitimate users, excessive AWS costs                                                                         |
| **Affected Assets** | Service availability                                                                                                                     |

**Mitigations implemented**:

- Token-bucket rate limiter: 10 messages/minute per session (burst of 10), enforced in `websocket_server.py`
- Maximum 100 concurrent sessions enforced by `SessionManager`; idle sessions evicted after 1 hour
- 64 KB WebSocket message size limit
- WebSocket `/ws` upgrades validate the `Origin` header against the CORS allowlist before accepting; cross-origin browser connections are rejected with close code 1008
- `CORS_ORIGINS` is automatically wired to the CloudFront distribution URL via CDK L1 override at deployment time, ensuring the Origin allowlist includes the correct cloud endpoint

**Residual risk — CloudFront WAF**: No `aws_wafv2` web ACL is attached to the CloudFront distribution. cdk-nag finding `AwsSolutions-CFR2` is **POC accepted risk** — the deployment is gated behind Cognito auth and the rate limiter, and L7 edge protection is deferred to post-POC hardening. Operators MUST attach a WAF web ACL before exposing the distribution to anonymous internet traffic at scale.

---

### T11 — Missing RBAC / Cross-Tenant Access

| Field               | Detail                                                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **STRIDE**          | Elevation of Privilege, Information Disclosure                                                                     |
| **Severity**        | High                                                                                                               |
| **Actor**           | Malicious authenticated user                                                                                       |
| **Precondition**    | Valid authentication credentials                                                                                   |
| **Attack**          | Access codebases or conversation histories belonging to other users — no resource-level authorization checks exist |
| **Impact**          | Unauthorized access to other users' proprietary source code and conversation data                                  |
| **Affected Assets** | Customer source code (A008), conversation history (A010)                                                           |

**Mitigation**: **POC accepted risk** — the system is designed for single-tenant deployment (one codebase per deployment instance). Multi-tenant RBAC must be implemented before any multi-user production deployment. See Assumption A004.

---

### T12 — Conversation Data Exposure (DynamoDB and AgentCore Memory)

| Field               | Detail                                                                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **STRIDE**          | Information Disclosure                                                                                                                                 |
| **Severity**        | Medium                                                                                                                                                 |
| **Actor**           | Insider with DynamoDB or AgentCore Memory read access                                                                                                  |
| **Precondition**    | Conversation logging or AgentCore Memory enabled                                                                                                       |
| **Attack**          | Read conversation history from DynamoDB or AgentCore Memory, which may contain sensitive code snippets, architectural details, or security discussions |
| **Impact**          | Exposure of sensitive conversation data                                                                                                                |
| **Affected Assets** | Conversation history (A010)                                                                                                                            |

**Mitigations implemented**:

- DynamoDB encrypted with AWS-owned keys by default; CMK available as opt-in
- DynamoDB records have a 90-day TTL (`expiry_ttl`) enforced by `DynamoDBMessageLogger`
- Messages exceeding 8.5 KB are truncated before storage (both DynamoDB and AgentCore Memory paths)
- Local conversation history files have permissions restricted to owner (`0o600`)
- AgentCore Memory is an optional feature; disabled by default

**Residual risk**: CMK encryption not enforced by default for DynamoDB. **POC accepted risk**.

---

### T13 — Supply Chain Dependency Compromise

| Field               | Detail                                                                                                    |
| ------------------- | --------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Spoofing, Tampering, Information Disclosure, Elevation of Privilege                                       |
| **Severity**        | High                                                                                                      |
| **Actor**           | Supply chain attacker                                                                                     |
| **Precondition**    | Third-party Python packages installed in the Docker image                                                 |
| **Attack**          | Compromise a dependency via typosquatting or package takeover to inject malicious code into the container |
| **Impact**          | Full container compromise, access to customer source code and IAM credentials                             |
| **Affected Assets** | All assets                                                                                                |

**Mitigations implemented**:

- **ASH (Automated Security Helper)** runs in CI/CD (`ash-scan` stage): includes Grype (CVE scanning), Syft (SBOM generation), cfn-nag (IaC scanning), and produces GitLab SAST and CycloneDX reports
- `pip-audit` integrated in CI/CD pipeline to scan for known CVEs in Python dependencies
- Dependencies pinned with exact versions in `requirements.txt`
- Dependabot configured for automated dependency update PRs
- Docker image built from a minimal base image; container runs as non-root user
- CI/CD lint stage includes private key detection (`grep -r "PRIVATE KEY"`) and large file detection

---

### T14 — Debug Endpoint Information Disclosure

| Field               | Detail                                                                                                     |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Information Disclosure, Elevation of Privilege                                                             |
| **Severity**        | Low                                                                                                        |
| **Actor**           | Authenticated attacker or misconfigured deployment                                                         |
| **Precondition**    | `ENABLE_DEBUG_ENDPOINTS=true` set in a non-development environment                                         |
| **Attack**          | Access the `/sessions` endpoint to enumerate all active sessions, user info, and session metadata          |
| **Impact**          | Exposure of active session IDs, user identifiers, and session timing data that could aid session hijacking |
| **Affected Assets** | Session tokens (A003), user info (A002)                                                                    |

**Mitigations implemented**:

- `/sessions` endpoint is only registered when `ENABLE_DEBUG_ENDPOINTS=true` (disabled by default)
- Endpoint requires authentication via `_require_auth_for_endpoint()` even when enabled
- CDK deployment does not set `ENABLE_DEBUG_ENDPOINTS`

**Residual risk**: Misconfigured deployments that set `ENABLE_DEBUG_ENDPOINTS=true` in production expose session metadata. Operators must ensure this flag is not set outside local development.

---

## 6. Residual Risks and Accepted Risks

The following risks are accepted for the POC release. They **must** be addressed before any multi-user or production deployment.

| ID  | Threat                             | Severity | Acceptance Rationale                                                     | Pre-Production Action Required                                              |
| --- | ---------------------------------- | -------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| T1  | Anonymous access in local/dev mode | Low      | By design for developer experience; CDK always enforces Cognito in cloud | Document clearly; enforce `ALLOW_ANONYMOUS=false` in any shared environment |
| T4  | HTTP on CloudFront → ALB leg       | Medium   | AWS Nitro System provides physical encryption; standard AWS pattern      | Add HTTPS listener on ALB for end-to-end TLS                                |
| T8  | Log injection (partial coverage)   | Medium   | `sanitize_for_log` covers most paths; structured logging deferred        | Migrate to structured JSON logging                                          |
| T11 | No RBAC / multi-tenant isolation   | High     | Single-tenant POC only                                                   | Implement resource-level authorization before multi-user deployment         |
| T12 | Conversation history without CMK   | Medium   | AWS-owned key encryption in place; CMK is opt-in                         | Enforce CMK for production deployments handling sensitive data              |

---

## 7. Assumptions

| ID   | Category          | Assumption                                                                                   | Impact if False                                                                          |
| ---- | ----------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| A001 | Authentication    | Amazon Cognito is properly configured in production with self-signup disabled                | Anonymous access to all features                                                         |
| A002 | Network           | VPC endpoints are configured for all AWS service access (S3, Bedrock, CloudWatch, ECR)       | AWS service traffic traverses public internet via NAT Gateway                            |
| A003 | AWS Services      | Amazon Bedrock does not retain or use customer prompts for model training                    | Customer source code sent in prompts could be exposed                                    |
| A004 | Authorization     | No RBAC exists — all authenticated users have equal access to all features and codebases     | Any authenticated user can access any codebase in multi-tenant scenarios                 |
| A005 | Operations        | `ENABLE_DEBUG_ENDPOINTS` is not set to `true` in any non-development deployment              | Active session metadata exposed to authenticated users                                   |
| A006 | Optional Features | AgentCore Memory and DynamoDB conversation logging are disabled unless explicitly configured | Conversation content stored in external services beyond the application's direct control |

---

_This threat model was produced using the STRIDE methodology. It was initially generated by the Threat Modeling MCP Server and finalized manually to reflect security hardening completed for open-source release. It should be reviewed and updated whenever significant architectural changes are made._
