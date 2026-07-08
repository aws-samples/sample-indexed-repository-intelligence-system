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
- ALB/CloudFront Access Logs: Encrypted by default in S3
- Amazon VPC Flow Logs: Encrypted by default with AWS-owned keys

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

**Client to CloudFront:**

- HTTPS enforced (HTTP redirects to HTTPS)
- TLS 1.2+ with strong cipher suites
- AWS-managed SSL certificate

**CloudFront to Application Load Balancer:**

- HTTP over AWS internal network
- Protected by security groups (CloudFront prefix list only)
- Physical layer encryption via AWS Nitro System

**Application to AWS Services:**

- All AWS API calls use HTTPS (TLS 1.2+)
- Amazon VPC endpoints for private connectivity to S3, Amazon Bedrock, CloudWatch
- Cognito JWKS validation over HTTPS

**Configuration:**

No configuration required. Encryption in transit is enabled by default.

### Data Residency

IRIS processes data in the AWS region where the customer deploys the stack. Codebase artifacts remain in the S3 bucket specified during deployment and do not leave the customer's AWS account.

**Data Flow:**

1. Customer uploads codebase to their S3 bucket
2. ECS tasks read from the customer's S3 bucket (same region)
3. Amazon Bedrock API calls use regions configured by the customer
4. All processing occurs in the customer's AWS account

### Data Retention and Deletion

**Customer Content:**

- Stored in the customer's S3 bucket — the customer controls retention policies
- Delete objects from the S3 bucket to remove customer content
- No customer content stored in IRIS infrastructure

**Service Data:**

- CloudWatch Logs: Configurable retention (default 7 days)
- Access Logs: Stored in S3 with lifecycle policies
- In-memory data: Cleared when ECS tasks terminate

**Configuration:**

```yaml
# infra/config.yaml
logging:
  retention_days: 7 # CloudWatch Logs retention
```

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

- ECS Task Role: Grants permissions to access AWS services
- ECS Execution Role: Grants permissions to pull images and write logs
- No IAM users or long-lived credentials

**Least Privilege:**

- Amazon Bedrock: `Invoke*` and `Converse*` actions (required for AI functionality)
- S3: `GetObject` and `ListBucket` scoped to your bucket
- KMS: `Decrypt` and `DescribeKey` scoped to your key (if CMK configured)
- CloudWatch: `CreateLogStream` and `PutLogEvents` for application logs

**Example IAM Policy:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:Invoke*", "bedrock:Converse*"],
      "Resource": "*"
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

### Session Management

**JWT Tokens:**

- Issued by Cognito upon successful authentication
- Stored in browser memory (not localStorage or cookies)
- Automatic expiration and refresh
- Validated on every WebSocket connection

**WebSocket Security:**

- JWT token required for WebSocket upgrade
- Token validated against Cognito JWKS endpoint
- Connections terminated on token expiration

---

## Logging and Monitoring

### CloudWatch Logs

IRIS logs all application events to CloudWatch Logs.

**Log Groups:**

- `/ecs/frontend` - React application logs
- `/ecs/backend` - Python backend logs

**Logged Events:**

- Authentication attempts (success/failure)
- API requests and responses
- Error conditions and exceptions
- WebSocket connections and disconnections

**Log Sanitization:**

- PII automatically redacted from logs
- Sensitive data never logged
- Request/response bodies sanitized

**Configuration:**

```yaml
# infra/config.yaml
logging:
  retention_days: 7 # Adjust based on compliance requirements
```

For compliance requirements (e.g., 10-year retention), increase `retention_days` to 3650.

### Access Logs

**Application Load Balancer:**

- HTTP request metadata logged to S3
- Includes source IP, request path, response codes
- No request/response bodies

**CloudFront:**

- CDN request metadata logged to S3
- Includes edge location, viewer location, cache status
- No request/response bodies

**Amazon VPC Flow Logs:**

- Network traffic metadata logged to CloudWatch
- Includes source/destination IPs, ports, protocols
- No packet contents

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
- Amazon VPC isolation and network security

**HIPAA:**

- Customer Managed Keys for PHI encryption
- Access logging and monitoring
- Network isolation via Amazon VPC
- No PHI in application logs

**PCI-DSS:**

- Strong encryption (AES-256 at rest, TLS 1.2+ in transit)
- Access controls via IAM and Cognito
- Logging and monitoring
- Network segmentation

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
3. Set log retention to 10 years (3650 days)
4. Deploy in FedRAMP-authorized regions

```yaml
# infra/config.yaml
codebase_artifacts:
  bucket: "your-bucket"
  kms_key_arn: "arn:aws:kms:us-gov-west-1:account:key/key-id"

logging:
  retention_days: 3650 # 10 years
```

**For HIPAA Compliance:**

1. Sign AWS Business Associate Addendum (BAA)
2. Use Customer Managed Keys for PHI
3. Enable CloudTrail and Amazon VPC Flow Logs
4. Implement access controls via Cognito

---

## Resilience

### High Availability

**Multi-AZ Deployment:**

- Amazon VPC spans 2 Availability Zones (configurable)
- Application Load Balancer distributes traffic across AZs
- ECS tasks can run in multiple AZs
- CloudFront provides global edge caching

**Configuration:**

```yaml
# infra/config.yaml
service:
  desired_count: 2 # Run tasks in multiple AZs
  max_azs: 2 # Use 2 Availability Zones
```

### Fault Tolerance

**Automatic Recovery:**

- ECS automatically restarts failed tasks
- Health checks monitor application status
- ALB removes unhealthy targets from rotation
- CloudFront fails over to healthy origins

**Health Checks:**

- Frontend: HTTP GET to `/` (port 3000)
- Backend: HTTP GET to `/health` (port 8000)
- Interval: 30 seconds
- Timeout: 10 seconds
- Unhealthy threshold: 3 consecutive failures

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

IRIS is designed to implement defense-in-depth network security controls.

**Amazon VPC Configuration:**

- Private subnets for ECS tasks (no direct internet access)
- Public subnets for Application Load Balancer
- NAT Gateway for outbound internet access (Cognito only)
- Amazon VPC Flow Logs enabled

**Amazon VPC Endpoints:**

- S3 Gateway Endpoint (private S3 access)
- Amazon Bedrock Runtime Interface Endpoint
- CloudWatch Logs Interface Endpoint
- ECR API and Docker Interface Endpoints

**Security Groups:**

_Application Load Balancer:_

- Ingress: Port 80 from CloudFront prefix list only
- Egress: Port 3000 to ECS tasks

_ECS Tasks:_

- Ingress: Port 3000 and 8000 from ALB only
- Egress: HTTPS (443) to Amazon VPC endpoints and Cognito
- Egress: DNS (53) for name resolution
- Port 25 (SMTP) explicitly blocked

**Configuration:**

See [Network Security Guide](network-security.md) for detailed architecture.

### DDoS Protection

**AWS Shield Standard:**

- Automatic protection against common DDoS attacks
- Included at no additional cost
- Protects CloudFront and ALB

**CloudFront:**

- Global edge network absorbs traffic spikes
- Geographic restrictions available
- Rate limiting via AWS WAF (optional)

**Application Load Balancer:**

- Connection draining and request buffering
- Slow loris attack protection
- HTTP flood protection

### Container Security

**Non-Root Execution:**

- Containers run as non-root user `appuser`
- No sudo or root privileges
- File permissions restricted to application user

**Image Security:**

- Base images from official sources (Python, Node.js)
- Security patches applied during build
- Vulnerability scanning via ECR (optional)

**Runtime Security:**

- Read-only root filesystem (where possible)
- No privileged containers
- Resource limits enforced (CPU, memory)

---

## Configuration and Vulnerability Analysis

### Security Scanning

**Container Images:**

- Scan images with Amazon ECR image scanning
- Automated scanning on push
- CVE detection and reporting

**Dependencies:**

- Python: `pip-audit` for vulnerability scanning
- Node.js: `npm audit` for vulnerability scanning
- Regular updates to patch vulnerabilities

**Configuration:**

```bash
# Enable ECR scanning
aws ecr put-image-scanning-configuration \
  --repository-name iris \
  --image-scanning-configuration scanOnPush=true

# Scan Python dependencies
pip-audit

# Scan Node.js dependencies
npm audit
```

### Security Headers

IRIS implements security headers at multiple layers.

**CloudFront Response Headers:**

- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Strict-Transport-Security: max-age=47304000; includeSubDomains`
- `Content-Security-Policy: default-src 'self'`
- `Cache-Control: no-store, no-cache`

**Backend Middleware:**

- Security headers added to all HTTP responses
- CORS configured for frontend origin only
- No sensitive data in response headers

See [Security Headers Implementation](security-headers-implementation.md) for details.

### Vulnerability Management

**Container Image Patching:**

IRIS uses containerized deployments (ECS Fargate) with Python and Node.js base images. You are responsible for keeping container images patched and up-to-date.

**Enable ECR Image Scanning:**

Amazon ECR provides automated vulnerability scanning for container images using Amazon Inspector.

```bash
# Enable scanning on push for your ECR repositories
aws ecr put-image-scanning-configuration \
  --repository-name iris-backend \
  --image-scanning-configuration scanOnPush=true

aws ecr put-image-scanning-configuration \
  --repository-name iris-frontend \
  --image-scanning-configuration scanOnPush=true
```

**Patching Process:**

1. **Monitor for CVEs:**
   - Enable ECR image scanning (see above)
   - Subscribe to security advisories for Python and Node.js
   - Review ECR scan results regularly in AWS Console

2. **Update Base Images:**
   - Backend: Update Python base image in `backend/Dockerfile`
   - Frontend: Update Node.js base image in `frontend/Dockerfile`

3. **Update Dependencies:**
   - Python: Update `pyproject.toml` and rebuild
   - Node.js: Update `package.json` and rebuild

4. **Rebuild and Redeploy:**

   ```bash
   cd infra
   cdk deploy
   ```

5. **Verify Patching:**
   - Check ECR scan results after deployment
   - Verify no HIGH or CRITICAL vulnerabilities remain

**Patching Strategy:**

- Review ECR scan results weekly
- Patch CRITICAL vulnerabilities within 7 days
- Patch HIGH vulnerabilities within 30 days
- Update base images monthly for routine maintenance

**Monitoring:**

- Enable ECR image scanning for automated CVE detection
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
