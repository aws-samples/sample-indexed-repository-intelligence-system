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

IRIS is a cloud-native AI-powered code analysis and chat application built on AWS. Users upload codebases to Amazon S3; the system generates summaries and context using Amazon Bedrock (Claude models). The agent runs on Amazon Bedrock AgentCore Runtime — a serverless, fully managed backend — and the browser invokes the Runtime data-plane endpoint directly over HTTPS, streaming responses as Server-Sent Events (SSE).

### Components

| ID   | Component                    | Technology                | Hosting                                   |
| ---- | ---------------------------- | ------------------------- | ----------------------------------------- |
| C001 | React Frontend               | React 18+ / TypeScript    | Amazon CloudFront + private S3 (OAC)      |
| C002 | Amazon Bedrock AgentCore Runtime | Python / Strands agent | AWS Managed (serverless, per-session microVM) |
| C003 | Managed Cognito JWT Authorizer | AgentCore Runtime authorizer | AWS Managed                            |
| C004 | Amazon Bedrock               | Claude models             | AWS Managed                               |
| C005 | S3 Codebase Bucket           | Amazon S3                 | AWS Managed (external / pre-existing)     |
| C006 | Amazon Cognito               | Cognito User Pool + Client | AWS Managed                              |
| C007 | Amazon CloudWatch Logs       | CloudWatch                | AWS Managed                               |
| C008 | MCP Server                   | Python / stdio            | Local developer machine                   |

---

## 2. Security and Trust Boundaries

### Trust Zones

```
┌─────────────────────────────────────────────────────────────────────┐
│  UNTRUSTED — Public Internet                                        │
│  End users, browsers, IDE clients                                   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Edge Layer (MEDIUM trust)                                    │  │
│  │  CloudFront (HTTPS, OAC) → private S3 (static React app)      │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Managed Auth Boundary (enforced by AWS before compute)       │  │
│  │  AgentCore Runtime managed Cognito JWT authorizer             │  │
│  │                                                               │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  Application Layer (HIGH trust) — AWS Managed           │  │  │
│  │  │  AgentCore Runtime: per-session isolated microVM        │  │  │
│  │  │  (dedicated CPU/memory/filesystem, sanitized on exit)   │  │  │
│  │  │                                                         │  │  │
│  │  │  ┌───────────────────────────────────────────────────┐  │  │  │
│  │  │  │  AWS Managed Services (HIGH trust)                │  │  │  │
│  │  │  │  Bedrock · S3 · Cognito · CloudWatch              │  │  │  │
│  │  │  └───────────────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  LOCAL DEVELOPER ENVIRONMENT (MEDIUM trust, separate boundary)      │
│  MCP Server (stdio) — no network exposure                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Boundary Definitions

| Boundary                        | Type     | Controls                                                                        |
| ------------------------------- | -------- | ------------------------------------------------------------------------------- |
| Internet → CloudFront (frontend)| Network  | HTTPS/TLS 1.2+, security headers, private S3 origin via OAC                      |
| Browser → AgentCore Runtime     | Protocol | HTTPS/TLS direct to the data-plane endpoint; managed Cognito JWT authorizer     |
| Managed authorizer → container  | Protocol | Token cryptographically validated (issuer/signature/expiry, `allowedClients`) before reaching the agent |
| Agent → AI Services             | Protocol | IAM execution role scoped to specific Bedrock inference-profile/model ARNs, TLS |
| Agent → S3 (optional)           | Protocol | IAM execution role, read-only `GetObject`/`ListBucket` scoped to the bucket, TLS |
| Local → MCP Server              | Process  | stdio only; path containment enforced in three layers                           |

---

## 3. Data Flows

### DF1 — Static Frontend Delivery

```
Browser → CloudFront (HTTPS, OAC) → private S3 bucket → React app returned to Browser
```

**Data in transit**: Static assets (HTML/JS/CSS), no user data
**Encrypted**: Yes (HTTPS browser→CloudFront; CloudFront→S3 over HTTPS; S3 bucket private via OAC)

### DF2 — Authenticated Chat Session

```
Browser → AgentCore Runtime data-plane endpoint (HTTPS)
          POST https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/invocations
          Authorization: Bearer <Cognito access token>
       → managed Cognito JWT authorizer validates the token (before the container)
       → per-session microVM (agent) → Bedrock (HTTPS) → SSE stream back to Browser
```

**Data in transit**: Cognito access token, user queries (may contain code context), LLM responses
**Encrypted**: Yes (HTTPS end to end, browser→data-plane; agent→Bedrock over TLS)

### DF3 — Codebase Analysis

```
S3 Bucket (external) → agent microVM (HTTPS, read-only GetObject/ListBucket)
                     → Bedrock (HTTPS) [summarization]
```

**Data in transit**: Customer source code, analysis artifacts
**Encrypted**: Yes; S3 SSE-S3 at rest (customer KMS CMK optional for the external bucket)

### DF4 — MCP Server (local)

```
IDE Plugin → MCP Server (stdio) → local file system
```

**Data in transit**: File paths, codebase content
**Encrypted**: N/A (local process communication)

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

| Component / Boundary           | S                         | T                   | R                  | I                         | D                     | E                          |
| ------------------------------ | ------------------------- | ------------------- | ------------------ | ------------------------- | --------------------- | -------------------------- |
| Browser ↔ AgentCore Runtime    | T6 (JWT replay)           | T4 (interception)   | T8 (log injection) | T5 (XSS)                  | T10 (DoS)             | T11 (no RBAC)              |
| Agent ↔ Bedrock                | T2 (prompt injection)     | —                   | —                  | T2 (data exfil)           | T10 (cost escalation) | T2 (agent tool abuse)      |
| Agent ↔ S3                     | T3 (IAM misconfiguration) | —                   | —                  | T3 (direct bucket access) | —                     | T7 (execution-role abuse)  |
| AgentCore microVM / agent code | T7 (execution-role abuse) | —                   | —                  | T7 (IAM abuse)            | —                     | T7 (agent-code compromise) |
| MCP Server (local)             | —                         | T9 (path traversal) | —                  | T9 (file disclosure)      | —                     | T9 (scope escape)          |
| Cognito / Managed Authorizer   | T1 (anon bypass, local)   | —                   | —                  | T6 (token replay)         | —                     | T1 (auth bypass)           |
| Supply Chain                   | T13 (dep compromise)      | T13                 | —                  | T13                       | —                     | T13                        |

---

## 5. Identified Threats and Mitigations

### T1 — Authentication Bypass (Local Mode)

| Field               | Detail                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Spoofing, Elevation of Privilege                                                                  |
| **Severity**        | Low (cloud not affected)                                                                          |
| **Actor**           | Unauthenticated attacker                                                                          |
| **Precondition**    | Running the agent locally with anonymous auth (`ALLOW_ANONYMOUS`), i.e. no managed authorizer     |
| **Attack**          | In a local run the frontend detects `authEnabled === false` and sends no bearer token; there is no managed authorizer in front of the local process |
| **Impact**          | Full unauthenticated access to all features in a local/dev environment                            |
| **Affected Assets** | User identity / access tokens (A009)                                                              |

**Mitigation**: In the cloud, the AgentCore Runtime is created with a managed Cognito JWT authorizer (`RuntimeAuthorizerConfiguration.using_cognito(user_pool, [user_pool_client])`), which validates the bearer token before any request reaches the container — the anonymous path cannot be reached in the deployed Runtime. Anonymous access exists only for LOCAL runs (`ALLOW_ANONYMOUS`) and is documented as dev-only. **POC accepted risk** for local development.

---

### T2 — Prompt Injection via Agentic Framework

| Field               | Detail                                                                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Tampering, Information Disclosure, Elevation of Privilege                                                                                                             |
| **Severity**        | Critical                                                                                                                                                              |
| **Actor**           | Authenticated user                                                                                                                                                    |
| **Precondition**    | Authenticated access to the chat endpoint                                                                                                                             |
| **Attack**          | Crafted prompts manipulate the LLM agent into revealing system prompts, accessing unauthorized files via the file retrieval agent, or executing unintended tool calls |
| **Impact**          | Unauthorized access to customer source code, system prompt exfiltration, unintended tool execution                                                                    |
| **Affected Assets** | Customer source code (A008), LLM prompts/responses (A011)                                                                                                             |

**Mitigations implemented**:

- Amazon Bedrock Guardrails support is wired through the agent creation path (`iris/agentic_chat.py`) and applied to model invocations when configured. Configuration is **opt-in**: the operator creates a Guardrail in the Amazon Bedrock console (or via CDK) and sets `guardrail_id` in `infra/config.yaml`. When `guardrail_id` is set, `infra/stack.py` grants the AgentCore Runtime execution role `bedrock:ApplyGuardrail` scoped to that ARN. Deployments without `guardrail_id` are unprotected at this layer — operators MUST configure a Guardrail before exposing the service to untrusted users.
- User-supplied file content is wrapped in explicit `<file_content>` markers in the prompt so the model can distinguish untrusted file data from instructions
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

- S3 Block Public Access enforced (all stack buckets use `BlockPublicAccess.BLOCK_ALL`)
- The AgentCore execution role's S3 access is read-only (`GetObject`/`ListBucket`) and scoped to the specific codebase-artifacts bucket ARN
- `enforce_ssl` requires TLS for bucket access
- SSE-S3 encryption at rest enforced (customer KMS CMK optional for the external codebase bucket)

---

### T4 — Token / Response Interception in Transit

| Field               | Detail                                                                        |
| ------------------- | ----------------------------------------------------------------------------- |
| **STRIDE**          | Information Disclosure, Tampering                                             |
| **Severity**        | Low                                                                           |
| **Actor**           | Attacker positioned on the network path between the browser and AWS           |
| **Precondition**    | Ability to intercept or tamper with browser ↔ AWS traffic                     |
| **Attack**          | Capture the Cognito access token, user queries, or AI responses in transit    |
| **Impact**          | Exposure of authentication tokens and sensitive code context                  |
| **Affected Assets** | Access tokens (A009), LLM prompts/responses (A011)                            |

**Mitigation**: All traffic is encrypted end to end with TLS. The browser reaches the static frontend over HTTPS (browser → CloudFront, `REDIRECT_TO_HTTPS`, TLS 1.2 minimum) and invokes the AgentCore Runtime data-plane endpoint (`https://bedrock-agentcore.{region}.amazonaws.com/...`) directly over HTTPS. There is no unencrypted internal hop between an edge tier and the application — the browser talks to the AWS data plane directly. The agent's calls to Amazon Bedrock and Amazon S3 also use TLS.

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
- Amazon CloudFront applies the AWS-managed `SECURITY_HEADERS` response headers policy to the static frontend (`X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy`, `Strict-Transport-Security`)
- A Content-Security-Policy is applied to the static app for local development via `frontend/serve.json` (`frame-ancestors 'none'`); see [Security Headers Implementation](security-headers-implementation.md)

---

### T6 — JWT Token Replay / Session Hijacking

| Field               | Detail                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------- |
| **STRIDE**          | Spoofing, Information Disclosure                                                            |
| **Severity**        | High                                                                                        |
| **Actor**           | External attacker with a stolen access token                                                |
| **Precondition**    | Attacker obtains a valid Cognito access token (e.g., via network interception or XSS)       |
| **Attack**          | Replay the access token as a bearer token to invoke the Runtime and impersonate the user    |
| **Impact**          | Full access to the impersonated user's session and codebase analysis                        |
| **Affected Assets** | Access tokens (A009)                                                                        |

**Mitigations implemented**:

- The AgentCore Runtime's managed Cognito JWT authorizer validates the bearer token cryptographically (issuer, RS256 signature, and expiry) against the Cognito user pool's OIDC discovery document, and matches `allowedClients` against the token's `client_id` claim — this happens before the request reaches the container, so token verification is handled by the managed layer rather than application code
- The frontend sends the Cognito **access token** (carries `client_id`), not the ID token, so the authorizer's `allowedClients` check is enforced
- Cognito access tokens are short-lived and carry an `exp` claim; expired tokens are rejected by the authorizer
- Tokens are held in browser memory (via the Amplify auth session), not in `localStorage` or cookies, reducing theft surface
- Transport is HTTPS end to end (see T4), limiting interception opportunities

---

### T7 — Agent-Code Compromise / Execution-Role Abuse

| Field               | Detail                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **STRIDE**          | Elevation of Privilege, Information Disclosure                                                                                 |
| **Severity**        | High                                                                                                                           |
| **Actor**           | Attacker who achieves code execution in the agent process                                                                      |
| **Precondition**    | Supply chain compromise (see T13) or a successful code-execution exploit against the agent                                    |
| **Attack**          | Abuse the AgentCore Runtime execution-role credentials available to the agent process to call Amazon Bedrock, Amazon S3, and (if configured) AWS KMS |
| **Impact**          | Access limited to the AWS services and resources the execution role is scoped to, including read access to customer source code |
| **Affected Assets** | IAM execution-role credentials (A012)                                                                                          |

**Mitigations implemented**:

- The AgentCore Runtime runs each session in an isolated, AWS-managed microVM; there is no customer-managed EC2-style instance metadata service to harvest, and the microVM is sanitized on session termination
- Execution role scoped to specific Bedrock inference-profile and foundation-model ARNs (not `bedrock:*`); the model/region wildcard carries a documented `AwsSolutions-IAM5` cdk-nag suppression
- Bedrock Guardrail permission (when configured) scoped to the specific Guardrail ARN
- S3 access is read-only and scoped to the specific codebase-artifacts bucket ARN
- KMS `Decrypt`/`DescribeKey` (when a CMK is configured) scoped to the specific key ARN
- CloudWatch Logs / X-Ray / workload-identity permissions are construct-managed with documented cdk-nag suppressions for the unavoidable wildcards
- Agent container runs as a non-root user (`appuser`)

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
| **Impact**          | Access to sensitive files on the developer's machine (MCP) or within the agent microVM (backend) |
| **Affected Assets** | Customer source code (A008), local credentials                                               |

**Mitigations implemented — three independent layers**:

1. **`iris_mcp/mcp_server.py` `validate_file_within_codebase()`**: `Path.resolve().relative_to(codebase_root)` — raises `ValueError` on escape; applied before any file read in the MCP server
2. **`iris/agents/utils.py` `read_multiple_files()`**: Same `resolve().relative_to()` check applied to every path in the file list before reading
3. **`iris/file_system/file_utils.py` `read_source()`**: Same containment check applied at the lowest-level file read function

MCP server communicates via stdio only — no network port exposed.

---

### T10 — Invocation Flooding / Bedrock Cost Escalation

| Field               | Detail                                                                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Denial of Service                                                                                                                        |
| **Severity**        | High                                                                                                                                     |
| **Actor**           | Authenticated user (or holder of a valid access token)                                                                                   |
| **Precondition**    | A valid Cognito access token accepted by the managed authorizer                                                                          |
| **Attack**          | Send a high volume of invocations (many sessions or rapid repeated prompts) to drive excessive Amazon Bedrock API calls and cost         |
| **Impact**          | Excessive AWS costs (primarily Amazon Bedrock usage); degraded experience                                                                |
| **Affected Assets** | Service availability, AWS spend                                                                                                          |

**Mitigations implemented / properties**:

- Unauthenticated requests are rejected by the managed Cognito JWT authorizer before reaching the agent, so anonymous flooding of the compute layer is not possible
- The AgentCore Runtime is serverless and scales per-session isolated microVMs, so one abusive session cannot exhaust a fixed-size, shared in-memory server the way a single long-lived container could — the resource-exhaustion concern shifts from container memory to per-session invocation volume and downstream Amazon Bedrock cost
- Amazon Bedrock enforces account-level model invocation quotas, which bound the blast radius of runaway usage
- Optional Amazon Bedrock Guardrails add per-invocation checks when configured

**Residual risk — rate limiting / WAF**: There is no application-level per-session rate limiter, and no `aws_wafv2` web ACL is attached to the CloudFront distribution (cdk-nag finding `AwsSolutions-CFR2`, documented and accepted for this proof-of-value — access is gated by the Cognito authorizer at the Runtime layer). Operators SHOULD add throttling (for example, via a WAF rate-based rule on the frontend and Amazon Bedrock quota/budget alarms) and MUST review cost controls before exposing the service broadly. **POC accepted risk.**

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

### T12 — Conversation Data Exposure

| Field               | Detail                                                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Information Disclosure                                                                                                          |
| **Severity**        | Low                                                                                                                            |
| **Actor**           | Attacker who compromises the agent process, or an insider with Amazon Bedrock access                                          |
| **Precondition**    | Access to the running agent process, or to Amazon Bedrock request logging in the account                                      |
| **Attack**          | Read in-flight conversation content (which may contain sensitive code snippets, architectural details, or security discussions) |
| **Impact**          | Exposure of sensitive conversation data                                                                                        |
| **Affected Assets** | Conversation history (A010)                                                                                                    |

**Mitigations / properties**:

- **No persistent conversation store is deployed.** The current stack provisions no Amazon DynamoDB table and no AgentCore Memory resource. Conversation history exists only in the memory of the per-session AgentCore microVM for the life of that session.
- Each session's microVM (including its memory) is isolated and sanitized on session termination, so conversation content does not persist or leak across sessions after teardown.
- Optional persistence capabilities exist in the codebase (a DynamoDB message logger and an AgentCore Memory hook provider) but are **not** wired into the deployed agent and are **not** provisioned by the stack. If an operator later enables either, conversation content would be stored in an external AWS-managed service and MUST be protected accordingly (encryption, retention/TTL, and CMK for sensitive data).

**Residual risk**: Conversation content is sent to Amazon Bedrock for inference (see A003) and is present in agent memory during processing. **POC accepted risk.**

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

### T14 — Auxiliary Read Action Information Disclosure

| Field               | Detail                                                                                                     |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| **STRIDE**          | Information Disclosure                                                                                     |
| **Severity**        | Low                                                                                                        |
| **Actor**           | Authenticated user                                                                                         |
| **Precondition**    | A valid Cognito access token accepted by the managed authorizer                                            |
| **Attack**          | Invoke the non-chat actions (`config`, `codebase_info`, `generate_context`) to read codebase metadata such as the codebase directory, file tree, and evaluation statistics |
| **Impact**          | Exposure of codebase structure/metadata to any authenticated user                                          |
| **Affected Assets** | Customer source code metadata (A008)                                                                       |

**Mitigations implemented**:

- All actions are served through the same AgentCore Runtime entrypoint and are therefore gated by the managed Cognito JWT authorizer — unauthenticated callers cannot reach them
- The actions return only codebase directory/metadata and best-effort statistics; there is no session-enumeration or user-listing endpoint in the Runtime
- Errors are returned as generic messages and sanitized before logging (`security_utils.py`), avoiding leakage of internal details

**Residual risk**: Because there is no per-user authorization (see T11), any authenticated user can read the single deployment's codebase metadata. **POC accepted risk** for single-tenant deployments.

---

## 6. Residual Risks and Accepted Risks

The following risks are accepted for the POC release. They **must** be addressed before any multi-user or production deployment.

| ID  | Threat                                | Severity | Acceptance Rationale                                                     | Pre-Production Action Required                                              |
| --- | ------------------------------------- | -------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| T1  | Anonymous access in local mode        | Low      | By design for developer experience; the managed Cognito authorizer always gates the cloud Runtime | Document clearly; do not enable `ALLOW_ANONYMOUS` in any shared environment |
| T8  | Log injection (partial coverage)      | Medium   | `sanitize_for_log` covers most paths; structured logging deferred        | Migrate to structured JSON logging                                          |
| T10 | No rate limiting / WAF                 | High     | Access gated by Cognito authorizer; WAF out of scope for POV (`CFR2`)    | Add WAF rate-based rules and Amazon Bedrock quota/budget alarms             |
| T11 | No RBAC / multi-tenant isolation      | High     | Single-tenant POC only                                                   | Implement resource-level authorization before multi-user deployment         |

---

## 7. Assumptions

| ID   | Category          | Assumption                                                                                   | Impact if False                                                                          |
| ---- | ----------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| A001 | Authentication    | Amazon Cognito is properly configured, self-signup disabled, and the AgentCore Runtime's managed Cognito authorizer is enabled in the cloud | Anonymous access to all features                                        |
| A002 | Networking        | The AgentCore Runtime and its managed authorizer, plus CloudFront/S3 (OAC), provide the network isolation — there is no customer-managed VPC to configure | Reliance on AWS-managed network controls being correctly provisioned by the stack |
| A003 | AWS Services      | Amazon Bedrock does not retain or use customer prompts for model training                    | Customer source code sent in prompts could be exposed                                    |
| A004 | Authorization     | No RBAC exists — all authenticated users have equal access to all features and codebases     | Any authenticated user can access any codebase in multi-tenant scenarios                 |
| A005 | Deployment        | The single deployment serves a single codebase (single-tenant)                               | Cross-tenant exposure if a shared deployment serves multiple codebases without RBAC      |
| A006 | Optional Features | No persistent conversation store is deployed; the optional DynamoDB logger and AgentCore Memory hook are not wired in unless an operator explicitly enables them | If enabled, conversation content would be stored in an external service beyond the application's direct control |

---

_This threat model was produced using the STRIDE methodology. It was initially generated by the Threat Modeling MCP Server and finalized manually to reflect security hardening completed for open-source release. It should be reviewed and updated whenever significant architectural changes are made._
