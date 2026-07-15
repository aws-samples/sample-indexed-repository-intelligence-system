<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Network Security Implementation

## Overview

IRIS is a serverless application built on Amazon Bedrock AgentCore Runtime and Amazon
CloudFront. It has no customer-managed network layer — there are no VPCs, subnets,
security groups, NAT gateways, or load balancers to configure. Network isolation is
provided by AWS-managed services, and all traffic reaching IRIS is encrypted in transit
and authenticated at the edge of the managed layer.

## Architecture

```
Browser ──HTTPS──▶ Amazon CloudFront (OAC) ──▶ Private Amazon S3 bucket   (static React app)

Browser ──HTTPS──▶ Amazon Bedrock AgentCore Runtime data-plane            (chat / API)
                   https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/invocations
                   │
                   ├─ managed Cognito JWT authorizer validates the bearer token
                   │  BEFORE the request reaches the container
                   │
                   └─▶ per-session isolated microVM (agent process)
                          └──▶ Amazon Bedrock (model invocation)
                          └──▶ Amazon S3 (codebase artifacts, read-only, optional)
```

There are two independent paths from the browser, both over HTTPS/TLS:

1. **Static frontend** — the React app is served from a private Amazon S3 bucket through
   Amazon CloudFront using Origin Access Control (OAC). The bucket is never public.
2. **Application (chat) traffic** — the browser invokes the AgentCore Runtime data-plane
   endpoint directly. The Runtime's managed Amazon Cognito JWT authorizer validates the
   bearer token before any request reaches the agent container.

The AgentCore Runtime runs in AgentCore's AWS-managed network (`PUBLIC` network mode).
Customers do not provision or manage VPCs, subnets, security groups, NACLs, or NAT
gateways; the underlying compute network is owned and operated by the Runtime service.

## Security Controls

### 1. Inbound Traffic — Static Frontend (Amazon CloudFront + Amazon S3)

- **Private origin bucket**: the frontend S3 bucket has `BlockPublicAccess.BLOCK_ALL`;
  it is reachable only through CloudFront via Origin Access Control (OAC).
- **HTTPS enforced**: the CloudFront distribution uses
  `viewer_protocol_policy = REDIRECT_TO_HTTPS`, so HTTP viewer requests are redirected to
  HTTPS.
- **TLS 1.2 minimum**: `minimum_protocol_version = TLS_V1_2_2021`.
- **Security response headers**: the AWS-managed `ResponseHeadersPolicy.SECURITY_HEADERS`
  policy is attached at the edge (see [Security Headers Implementation](security-headers-implementation.md)).
- **SPA routing**: 403/404 responses are mapped to `/index.html` for client-side routing.

### 2. Inbound Traffic — Application (Amazon Bedrock AgentCore Runtime)

- **Direct HTTPS to the data plane**: the browser calls
  `https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/invocations` over TLS
  and reads a Server-Sent Events (SSE) response. There is no persistent WebSocket and no
  self-managed HTTP server exposed to the internet.
- **Managed authentication at the boundary**: the Runtime's managed Cognito JWT authorizer
  cryptographically validates the bearer token (issuer, signature, and expiry against the
  Cognito user pool's OIDC discovery document, with `allowedClients` matched against the
  token's `client_id` claim) **before** the request is forwarded to the container. Requests
  without a valid token never reach the agent.
- **Session isolation**: each `runtimeSessionId` runs in its own isolated microVM with
  dedicated CPU, memory, and filesystem. The microVM (including its memory) is sanitized on
  session termination, so no state leaks between sessions.

### 3. Outbound Traffic — Agent to AWS Services

The agent process inside the microVM reaches AWS services over the AgentCore-managed
network using its scoped execution role (see [Security](security.md#identity-and-access-management)):

- **Amazon Bedrock**: model invocation (`bedrock:Invoke*`, `bedrock:Converse*`), scoped to
  inference-profile and foundation-model ARNs.
- **Amazon S3** (optional): read-only access (`s3:GetObject`, `s3:ListBucket`) to the
  external codebase-artifacts bucket, plus optional `kms:Decrypt` when a customer managed
  key is configured.
- **Amazon CloudWatch Logs / AWS X-Ray**: telemetry, managed by the AgentCore Runtime
  construct.

All of these calls use HTTPS (TLS 1.2+). Egress is bounded by the execution role's
least-privilege policy rather than by customer-managed security groups.

### 4. Edge Protection

- **AWS Shield Standard** protects the Amazon CloudFront distribution automatically at no
  additional cost.
- **AWS WAF** is out of scope for this proof-of-value. Access to the application is gated by
  the managed Cognito authorizer at the Runtime layer, which is why the deployment carries a
  documented `AwsSolutions-CFR2` cdk-nag suppression. Operators who expose the distribution
  to broad anonymous internet traffic SHOULD attach a WAF web ACL to CloudFront.

## Security Benefits

1. **No customer-managed network attack surface**: no VPCs, security groups, NACLs, or NAT
   gateways to misconfigure.
2. **Authentication before compute**: the managed authorizer rejects unauthenticated
   requests before they reach application code.
3. **Strong tenant/session isolation**: per-session microVMs with sanitized teardown.
4. **Private static origin**: the frontend bucket is never publicly reachable (OAC only).
5. **Encryption everywhere in transit**: browser → CloudFront and browser → AgentCore
   data plane are both HTTPS; agent → AWS services is HTTPS.
6. **Least-privilege egress**: the agent can only reach the specific AWS services and
   resources granted to its execution role.

## Compliance

This implementation satisfies the following network security objectives:

- ✅ Restrict inbound access to authenticated, business-justified paths (Cognito authorizer)
- ✅ Keep the static origin private (CloudFront OAC; S3 Block Public Access)
- ✅ Enforce HTTPS/TLS 1.2+ on all viewer and service traffic
- ✅ Restrict egress via least-privilege IAM on the execution role
- ✅ Isolate workloads per session (dedicated microVM, sanitized on termination)

## Verification

### Confirm the static frontend origin is private

```bash
# Bucket should report BlockPublicAccess = ALL true
aws s3api get-public-access-block --bucket <frontend-bucket-name>

# CloudFront distribution should use OAC and REDIRECT_TO_HTTPS
aws cloudfront get-distribution-config --id <distribution-id>
```

### Confirm the Runtime enforces authentication

1. Invoke the data-plane endpoint **without** an `Authorization` header — the request MUST
   be rejected by the managed authorizer (HTTP 401/403) before reaching the agent.
2. Invoke with a valid Cognito **access** token — the request succeeds and streams SSE
   events.

```bash
# Expect a 401/403 (no bearer token)
curl -i -X POST \
  "https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<arn>/invocations?qualifier=DEFAULT" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"hello"}'
```

### Inspect the execution role (egress scope)

```bash
aws iam list-role-policies --role-name <AgentCoreExecutionRole>
aws iam get-role-policy --role-name <AgentCoreExecutionRole> --policy-name <policy>
```

## References

- [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html)
- [Restricting access to an Amazon S3 origin (CloudFront OAC)](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [Amazon CloudFront and AWS Shield Standard](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-overview.html)
- [Amazon Cognito user pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-identity-pools.html)
