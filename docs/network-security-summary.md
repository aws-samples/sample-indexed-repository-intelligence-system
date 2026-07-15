<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Network Security Implementation Summary

This is a condensed companion to [network-security.md](network-security.md). IRIS is
serverless: it runs on Amazon Bedrock AgentCore Runtime with an Amazon CloudFront + Amazon
S3 static frontend. There is no customer-managed network layer (no VPC, subnets, security
groups, NACLs, or NAT gateways) to configure.

## Network Model

There are two independent, HTTPS-only paths from the browser:

```
Browser ──HTTPS──▶ Amazon CloudFront (OAC) ──▶ Private Amazon S3 bucket   (static React app)

Browser ──HTTPS──▶ Amazon Bedrock AgentCore Runtime data-plane            (chat / API)
                   └─ managed Cognito JWT authorizer validates the token
                      before it reaches the per-session microVM
```

- **Static frontend**: served from a private S3 bucket through CloudFront using Origin
  Access Control (OAC). The bucket has `BlockPublicAccess.BLOCK_ALL` and is never public.
- **Application traffic**: the browser invokes the AgentCore Runtime data-plane endpoint
  directly. The managed Cognito JWT authorizer validates the bearer token before any request
  reaches the agent container.
- **Runtime network mode**: `PUBLIC`, managed by the AgentCore service. Each
  `runtimeSessionId` runs in its own isolated microVM (dedicated CPU/memory/filesystem,
  sanitized on termination).

## Security Controls

1. ✅ **Authentication before compute**: the managed Cognito authorizer rejects
   unauthenticated requests before they reach application code.
2. ✅ **Private static origin**: CloudFront OAC + S3 Block Public Access; the frontend bucket
   is never publicly reachable.
3. ✅ **HTTPS/TLS everywhere in transit**: browser → CloudFront and browser → AgentCore
   data plane are both HTTPS (TLS 1.2 minimum on CloudFront); agent → AWS services is HTTPS.
4. ✅ **Least-privilege egress**: the AgentCore execution role scopes the agent to specific
   Amazon Bedrock, Amazon S3, and telemetry actions/resources.
5. ✅ **Session isolation**: per-session microVMs, sanitized on teardown.
6. ⚠️ **AWS WAF is out of scope** for this proof-of-value (documented `AwsSolutions-CFR2`
   suppression); access is gated by the Cognito authorizer at the Runtime layer.

## Compliance Status

✅ **COMPLIANT** with the network security objectives for a serverless deployment:

- Inbound application access restricted to authenticated requests (Cognito authorizer)
- Static frontend origin kept private (CloudFront OAC only)
- HTTPS/TLS 1.2+ enforced on all viewer and service traffic
- Egress restricted by least-privilege IAM on the execution role
- Workloads isolated per session (dedicated microVM)

## Deployment Notes

**No customer network configuration is required** — there is no VPC, security group, or NAT
gateway to provision. The static frontend is built and synced to the S3 bucket by
`deploy.sh` after the stack exists (so the AgentCore Runtime ARN can be injected into the
frontend runtime config), and CloudFront is invalidated to serve the new build.

**Verification checklist:**

1. Confirm the frontend S3 bucket reports `BlockPublicAccess = ALL true`.
2. Confirm the CloudFront distribution uses OAC and `REDIRECT_TO_HTTPS`.
3. Confirm an unauthenticated call to the Runtime data-plane endpoint is rejected (401/403).
4. Confirm an authenticated call (valid Cognito access token) streams SSE events.
5. Confirm the execution role grants only the expected Bedrock/S3/telemetry permissions.

## Files

- `infra/stack.py` — AgentCore Runtime, Cognito user pool, CloudFront + S3 frontend
- `docs/network-security.md` — detailed documentation
- `docs/network-security-summary.md` — this summary
