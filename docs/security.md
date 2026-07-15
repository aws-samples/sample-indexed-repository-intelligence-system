<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Security in IRIS

Security is a shared responsibility between AWS and the customer. IRIS is built on AWS infrastructure and follows AWS security best practices. This document describes security features, controls, and configuration options available in IRIS.

> **Note:** Under the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/), AWS is responsible for security _of_ the cloud (infrastructure, managed services), while customers are responsible for security _in_ the cloud (application configuration, data, access management).

---

## Important Disclaimer

⚠️ The sample applications in this repository are provided as proof-of-value demonstrations and are not production-ready solutions. While all samples are required to pass automated security scanning (ASH) at the time they are contributed, this does not guarantee they are free of vulnerabilities. Additionally, samples are not guaranteed to receive security patches or dependency updates after publication.

Before deploying any sample to a production environment, you are solely responsible for:

- Conducting a thorough security review of the code
- Keeping dependencies up to date and patching known vulnerabilities
- Implementing appropriate access controls, encryption, and network security
- Performing penetration testing and vulnerability assessments
- Ensuring compliance with your organization's security requirements
- Determining how the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) applies to your use case

AWS offers a broad set of security tools and configurations to help you secure your workloads.

### Reporting a Vulnerability

If you discover a potential security issue in this project, we ask that you notify AWS/Amazon Security via our [vulnerability reporting page](https://aws.amazon.com/security/vulnerability-reporting/). Please do not create a public GitHub issue.

---

## Table of Contents

1. [Data Protection](#data-protection)
2. [Identity and Access Management](#identity-and-access-management)
3. [Logging and Monitoring](#logging-and-monitoring)
4. [Compliance Validation](#compliance-validation)
5. [Resilience](#resilience)
6. [Infrastructure Security](#infrastructure-security)
7. [Configuration and Vulnerability Analysis](#configuration-and-vulnerability-analysis)
8. [Security Best Practices](#security-best-practices)

---

## Data Protection

### Encryption at Rest

IRIS is designed to encrypt all data at rest to help protect your content.

**Customer Content (Your Codebase):**

- Stored in S3 buckets that the customer owns and controls
- Customers configure encryption settings on their S3 bucket
- Supports Customer Managed Keys (CMK) for enhanced control
- See [Encryption at Rest Guide](encryption-at-rest.md) for detailed configuration

**Service Data (Logs and Metadata):**

- CloudWatch Logs: Encrypted by default with AWS-owned keys
- CloudFront Access Logs: Stored in Amazon S3, encrypted with SSE-S3
- Amazon S3 Server Access Logs: Stored in Amazon S3, encrypted with SSE-S3

**Configuration:**

To use Customer Managed Keys for codebase artifacts:

```yaml
# infra/config.yaml
codebase_artifacts:
  bucket: "your-bucket-name"
  kms_key_arn: "arn:aws:kms:region:account:key/key-id"
```

See [Encryption at Rest documentation](encryption-at-rest.md) for complete setup instructions.

### Encryption in Transit

IRIS is designed to encrypt all data in transit using TLS 1.2 or higher.

**Browser to CloudFront (static frontend):**

- HTTPS enforced (HTTP redirects to HTTPS)
- TLS 1.2+ with strong cipher suites
- AWS-managed SSL certificate

**Browser to Amazon Bedrock AgentCore Runtime (chat/API):**

- The browser invokes the Runtime data-plane endpoint
  (`https://bedrock-agentcore.{region}.amazonaws.com/...`) directly over HTTPS/TLS
- The managed Cognito JWT authorizer validates the bearer token before the request reaches
  the agent container

**Agent to AWS Services:**

- All AWS API calls use HTTPS (TLS 1.2+)
- Amazon Bedrock model invocation and (optional) Amazon S3 reads over TLS

**Configuration:**

No configuration required. Encryption in transit is enabled by default.

### Data Residency

IRIS processes data in the AWS region where the customer deploys the stack. Codebase artifacts remain in the S3 bucket specified during deployment and do not leave the customer's AWS account.

**Data Flow:**

1. Customer uploads codebase to their S3 bucket
2. The AgentCore Runtime agent reads from the customer's S3 bucket (same region)
3. Amazon Bedrock API calls use regions configured by the customer
4. All processing occurs in the customer's AWS account

### Data Retention and Deletion

**Customer Content:**

- Stored in the customer's S3 bucket — the customer controls retention policies
- Delete objects from the S3 bucket to remove customer content
- No customer content stored in IRIS infrastructure

**Service Data:**

- CloudWatch Logs: The AgentCore Runtime emits application logs to the AWS-managed
  log group `/aws/bedrock-agentcore/runtimes/*`. The log group and its retention are
  managed by the Runtime; the IRIS stack does not create it or set a retention policy.
- Access Logs: Amazon CloudFront and Amazon S3 access logs are stored in S3
- In-memory / per-session data: The AgentCore Runtime runs each session in an isolated
  microVM whose memory and filesystem are sanitized when the session terminates

---

## Identity and Access Management

### Authentication

IRIS uses Amazon Cognito for user authentication.

**User Management:**

- Users created by administrators via AWS Console
- Email-based authentication with password requirements
- Multi-factor authentication (MFA) supported via Cognito
- No self-signup (admin-controlled access)

**Password Policy:**

- Minimum 8 characters
- Requires uppercase, lowercase, numbers, and symbols
- Email verification required

**Configuration:**

See [User Management Guide](user-management.md) for creating and managing users.

### Authorization

**IAM Roles:**

- AgentCore Runtime Execution Role: Trusts `bedrock-agentcore.amazonaws.com` and grants the
  agent permission to access AWS services
- No IAM users or long-lived credentials

**Least Privilege:**

- Amazon Bedrock: `Invoke*` and `Converse*` actions (required for AI functionality), scoped
  to inference-profile and foundation-model ARNs
- Amazon Bedrock Guardrails: `ApplyGuardrail` scoped to your Guardrail ARN (if configured)
- S3: `GetObject` and `ListBucket` scoped to your codebase-artifacts bucket (if configured)
- KMS: `Decrypt` and `DescribeKey` scoped to your key (if a CMK is configured for the bucket)
- CloudWatch Logs / AWS X-Ray / AgentCore workload identity: added and scoped by the
  AgentCore Runtime construct

**Example IAM Policy (execution role):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:Invoke*", "bedrock:Converse*"],
      "Resource": [
        "arn:aws:bedrock:*::inference-profile/*",
        "arn:aws:bedrock:*:account-id:inference-profile/*",
        "arn:aws:bedrock:*::foundation-model/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::your-bucket", "arn:aws:s3:::your-bucket/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:DescribeKey"],
      "Resource": "arn:aws:kms:region:account:key/key-id"
    }
  ]
}
```

> **Note:** The wildcard on Bedrock model/region is required because system-defined
> inference profiles and foundation models have no account ID in their ARNs and any
> configured model must be supported. This is covered by a documented `AwsSolutions-IAM5`
> cdk-nag suppression in `infra/stack.py`.

### Session Management

**JWT Tokens:**

- Issued by Cognito upon successful authentication
- The frontend sends the Cognito **access token** (which carries the `client_id` claim) as
  a bearer token on each Runtime invocation
- Automatic expiration and refresh handled by the Amplify auth session

**Request Authentication:**

- The AgentCore Runtime's managed Cognito JWT authorizer validates the bearer token
  cryptographically (issuer, signature, and expiry against the user pool's OIDC discovery
  document) **before** the request reaches the agent container
- `allowedClients` is set to the Cognito app client ID and is matched against the token's
  `client_id` claim (this is why the access token is sent, not the ID token — the ID token
  carries `aud` instead of `client_id` and would be rejected)
- Because validation happens at the managed layer, there is no application-level JWT
  verification code to maintain
- Each browser conversation uses a stable `runtimeSessionId`, and the Runtime isolates each
  session in its own microVM

---

## Logging and Monitoring

### CloudWatch Logs

IRIS logs all application events to CloudWatch Logs.

**Log Groups:**

- `/aws/bedrock-agentcore/runtimes/*` - AgentCore Runtime agent logs (managed by the
  Runtime construct)

**Logged Events:**

- Agent invocations and tool use
- Error conditions and exceptions
- Guardrail interventions (when a Guardrail is configured)

**Log Sanitization:**

- User-controlled values are sanitized before logging via `sanitize_for_log()` in
  `backend/security_utils.py` (strips newlines, carriage returns, ASCII control characters,
  and ANSI escape codes; truncates to 200 characters)
- Error types are logged via `get_safe_error_type()` rather than raw exception text
- Sensitive data is never logged

**Retention:**

The `/aws/bedrock-agentcore/runtimes/*` log group is created and managed by the AgentCore
Runtime; the IRIS stack does not set its retention policy. To enforce a specific retention
period (for example for compliance), set retention on that log group directly in CloudWatch
Logs, or add a `logs.CfnRetentionPolicy` / log-group construct to `infra/stack.py`.

### Access Logs

**Amazon CloudFront:**

- CDN request metadata logged to a dedicated Amazon S3 bucket
- Includes edge location, viewer location, cache status
- No request/response bodies

**Amazon S3 Server Access Logs:**

- Bucket access metadata (frontend bucket and CloudFront logs bucket) logged to a dedicated
  server-access-logs S3 bucket
- Includes requester, operation, and response status
- No object contents

### CloudTrail

AWS API calls made by IRIS are automatically logged to CloudTrail when you enable it in your AWS account.

**Logged API Calls:**

- S3: GetObject, ListBucket
- Amazon Bedrock: InvokeModel, Converse
- KMS: Decrypt, DescribeKey (if CMK configured)
- CloudWatch: PutLogEvents

**Configuration:**

Enable CloudTrail in your AWS account to capture all API activity:

```bash
aws cloudtrail create-trail \
  --name iris-trail \
  --s3-bucket-name your-cloudtrail-bucket
```

---

## Compliance Validation

IRIS offers features that can help customers address compliance requirements for regulated industries. Compliance is a shared responsibility — while IRIS provides security features that support compliance programs, customers are responsible for determining whether their use of AWS services meets applicable compliance requirements.

### Supported Compliance Programs

**FedRAMP:**

- Encryption at rest with FIPS-compliant KMS keys
- Encryption in transit with TLS 1.2+
- CloudTrail logging for audit trails
- Managed, isolated compute (per-session AgentCore microVMs)

**HIPAA:**

- Customer Managed Keys for PHI encryption
- Access logging and monitoring
- Managed workload isolation via AgentCore Runtime
- No PHI in application logs

**PCI-DSS:**

- Strong encryption (AES-256 at rest, TLS 1.2+ in transit)
- Access controls via IAM and Cognito
- Logging and monitoring
- Managed per-session workload isolation

**GDPR:**

- Data residency controls (deploy in EU regions)
- Customer-controlled encryption keys
- Data deletion capabilities
- Access logging for audit trails

**SOC 2:**

- Security controls documented
- Access management via IAM
- Encryption and logging
- Incident response capabilities

### Compliance Configuration

**For FedRAMP Compliance:**

1. Use Customer Managed KMS keys (SSE-KMS, not SSE-S3)
2. Enable CloudTrail in your account
3. Set log retention to 10 years (3650 days) on the AgentCore Runtime log group
   directly in CloudWatch Logs (the stack does not manage log retention)
4. Deploy in FedRAMP-authorized regions

```yaml
# infra/config.yaml
codebase_artifacts:
  bucket: "your-bucket"
  kms_key_arn: "arn:aws:kms:us-gov-west-1:account:key/key-id"
```

**For HIPAA Compliance:**

1. Sign AWS Business Associate Addendum (BAA)
2. Use Customer Managed Keys for PHI
3. Enable CloudTrail
4. Implement access controls via Cognito

---

## Resilience

### High Availability

**Managed, serverless availability:**

- Amazon Bedrock AgentCore Runtime is a fully managed, serverless backend — AWS handles
  capacity, availability, and scaling of the underlying compute
- Each session runs in its own microVM; the Runtime provisions per-session microVMs on
  demand, so there is no fixed pool of servers to size or balance
- Amazon CloudFront provides global edge caching and delivery for the static frontend
- The static frontend and CloudFront access/logging buckets have S3 versioning enabled

**Configuration:**

No availability configuration is required — capacity and multi-AZ resilience of the managed
Runtime are handled by AWS.

### Fault Tolerance

**Automatic Recovery:**

- The AgentCore Runtime manages the health and lifecycle of session microVMs; failed or
  terminated microVMs do not affect other sessions
- Amazon CloudFront serves the static frontend from a private Amazon S3 origin with global
  edge redundancy
- The Runtime provides a health-check (`/ping`) contract that is handled automatically by
  the AgentCore harness

### Backup and Recovery

**Customer Content:**

- Enable S3 versioning for point-in-time recovery
- Configure S3 lifecycle policies for backups
- Use S3 Cross-Region Replication for disaster recovery

**Configuration:**

```bash
# Enable S3 versioning
aws s3api put-bucket-versioning \
  --bucket your-bucket \
  --versioning-configuration Status=Enabled

# Configure lifecycle policy
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-bucket \
  --lifecycle-configuration file://lifecycle.json
```

---

## Infrastructure Security

### Network Security

IRIS is serverless and has no customer-managed network layer — there are no VPCs, subnets,
security groups, NACLs, or NAT gateways to configure. Network isolation is provided by the
AWS-managed AgentCore Runtime and Amazon CloudFront.

**Network model:**

- The static React app is served from a private Amazon S3 bucket through Amazon CloudFront
  using Origin Access Control (OAC); the bucket is never public
- The browser invokes the AgentCore Runtime data-plane endpoint directly over HTTPS; the
  managed Cognito JWT authorizer validates the token before it reaches the agent container
- The Runtime uses `PUBLIC` network mode, managed by the AgentCore service; each session
  runs in its own isolated microVM
- The agent reaches Amazon Bedrock and (optionally) Amazon S3 over HTTPS, bounded by the
  least-privilege execution role

**Configuration:**

See [Network Security Guide](network-security.md) for the detailed architecture.

### DDoS Protection

**AWS Shield Standard:**

- Automatic protection against common DDoS attacks
- Included at no additional cost
- Protects Amazon CloudFront

**Amazon CloudFront:**

- Global edge network absorbs traffic spikes for the static frontend
- Geographic restrictions available
- Rate limiting via AWS WAF (optional; out of scope for this proof-of-value)

**Amazon Bedrock AgentCore Runtime:**

- Access is gated by the managed Cognito JWT authorizer, so unauthenticated traffic is
  rejected before reaching the agent
- Per-session microVMs mean a heavy or abusive session is isolated from other sessions
  (resource-exhaustion and cost concerns are discussed in the [Threat Model](THREAT_MODEL.md))

### Container Security

**Non-Root Execution:**

- The agent container runs as the non-root user `appuser`
- No sudo or root privileges
- File permissions restricted to the application user

**Image Security:**

- Built from an official minimal base image, as an ARM64 image (required by the Runtime)
- Security patches applied during build

**Runtime Isolation:**

- Each session executes in its own AgentCore microVM with a dedicated, ephemeral filesystem
- The microVM and its memory are sanitized on session termination

---

## Configuration and Vulnerability Analysis

### Security Scanning

**Container Image:**

- The agent container image is built as part of the CDK deployment; scan it with your
  registry's image scanning (for example, Amazon ECR image scanning) if you push it to a
  repository
- CVE detection and reporting

**Dependencies:**

- Python: `pip-audit` for vulnerability scanning
- Node.js: `npm audit` for vulnerability scanning
- Regular updates to patch vulnerabilities

**Configuration:**

```bash
# Scan Python dependencies
pip-audit

# Scan Node.js dependencies
npm audit
```

### Security Headers

IRIS applies security headers to the static frontend at the Amazon CloudFront edge using
the AWS-managed `ResponseHeadersPolicy.SECURITY_HEADERS` policy.

**CloudFront Response Headers (managed policy):**

- `Strict-Transport-Security: max-age=31536000`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

XSS defense for AI-generated content is additionally enforced in the React rendering
pipeline (`skipHtml`, Mermaid `securityLevel: strict`, and DOMPurify).

See [Security Headers Implementation](security-headers-implementation.md) for details.

### Vulnerability Management

**Container Image Patching:**

The IRIS agent runs as a container image on Amazon Bedrock AgentCore Runtime, built from a
Python base image. You are responsible for keeping the image and its dependencies patched
and up-to-date.

**Patching Process:**

1. **Monitor for CVEs:**
   - Scan the built image with your registry's image scanning (for example, Amazon ECR
     image scanning with Amazon Inspector) if you push it to a repository
   - Subscribe to security advisories for Python and Node.js
   - Review scan results regularly

2. **Update Base Images:**
   - Agent: Update the Python base image in `backend/Dockerfile.agentcore` (or
     `backend/Dockerfile.agentcore_s3` for S3 mode)
   - Frontend build: Update the Node.js base image in `frontend/Dockerfile`

3. **Update Dependencies:**
   - Python: Update `pyproject.toml` and rebuild
   - Node.js: Update `package.json` and rebuild

4. **Rebuild and Redeploy:**

   ```bash
   cd infra
   cdk deploy
   ```

5. **Verify Patching:**
   - Re-scan the rebuilt image
   - Verify no HIGH or CRITICAL vulnerabilities remain

**Patching Strategy:**

- Review scan results weekly
- Patch CRITICAL vulnerabilities within 7 days
- Patch HIGH vulnerabilities within 30 days
- Update base images monthly for routine maintenance

**Monitoring:**

- Enable image scanning for automated CVE detection
- Subscribe to security advisories for dependencies
- Use AWS Security Hub for centralized vulnerability management
- Set up CloudWatch alarms for new HIGH/CRITICAL findings

---

## Security Best Practices

### Deployment Best Practices

1. **Use Customer Managed Keys**
   - Encrypt S3 bucket with your own KMS key
   - Maintain control over encryption keys
   - Enable key rotation

2. **Enable CloudTrail**
   - Log all API activity in your account
   - Store logs in secure S3 bucket
   - Set up alerts for suspicious activity

3. **Configure Log Retention**
   - Set appropriate retention based on compliance needs
   - Use S3 lifecycle policies for long-term storage
   - Enable log encryption

4. **Implement Least Privilege**
   - Review IAM policies regularly
   - Remove unused permissions
   - Use IAM Access Analyzer

5. **Enable Multi-Factor Authentication**
   - Require MFA for Cognito users
   - Use hardware tokens for admin accounts
   - Enforce MFA via Cognito policies

### Operational Best Practices

1. **Monitor Logs Regularly**
   - Set up CloudWatch alarms for errors
   - Review authentication failures
   - Investigate unusual patterns

2. **Update Dependencies**
   - Keep base images up to date
   - Patch vulnerabilities promptly
   - Test updates in non-production first

3. **Backup Customer Content**
   - Enable S3 versioning
   - Configure Cross-Region Replication
   - Test restore procedures

4. **Review Access Regularly**
   - Audit Cognito users quarterly
   - Remove inactive users
   - Review IAM role permissions

5. **Test Disaster Recovery**
   - Document recovery procedures
   - Test failover scenarios
   - Validate backup integrity

### Development Best Practices

1. **Secure Coding**
   - Validate all inputs
   - Sanitize outputs
   - Use parameterized queries

2. **Secrets Management**
   - Never hardcode credentials
   - Use IAM roles instead of access keys
   - Rotate credentials regularly

3. **Code Review**
   - Review security-sensitive changes
   - Use automated security scanning
   - Follow secure coding guidelines

4. **Testing**
   - Include security tests in CI/CD
   - Test authentication and authorization
   - Validate input sanitization

---

## Additional Resources

- [Encryption at Rest Guide](encryption-at-rest.md)
- [Network Security Guide](network-security.md)
- [User Management Guide](user-management.md)
- [Security Headers Implementation](security-headers-implementation.md)
- [Deployment Guide](deployment-guide.md)

## Support

For security concerns or questions:

- Contact your AWS AppSec Security Engineer
- Review AWS Security Best Practices documentation
- Consult AWS Well-Architected Framework Security Pillar

---

**Last Updated:** February 2026
**Document Version:** 1.0
