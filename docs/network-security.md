<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Network Security Implementation

## Overview

IRIS implements defense-in-depth network security controls following AWS best practices for least privilege network access.

## Architecture

```
Internet → CloudFront (HTTPS) → ALB (HTTP, CloudFront prefix list only) → ECS Tasks (private subnets)
                                                                                ↓
                                                                         VPC Endpoints + NAT Gateway
                                                                         (Amazon S3, Amazon Bedrock, Amazon CloudWatch, Amazon ECR + Amazon Cognito)
```

**Note:** NAT Gateway is required for Cognito JWT validation as Cognito does not offer VPC endpoints. VPC endpoints are used for all other AWS services to minimize NAT Gateway data transfer costs.

## Security Controls

### 1. Inbound Traffic Restrictions

**ALB Security Group:**

- Ingress: Only from CloudFront managed prefix list on port 80
- No direct internet access (0.0.0.0/0 blocked)
- CloudFront enforces HTTPS for end users

**ECS Task Security Group:**

- Ingress: Only from ALB security group
- No direct internet access
- Tasks deployed in private subnets (no public IPs)

### 2. Outbound Traffic Restrictions

**ECS Task Security Group Egress:**

- HTTPS (443): To Amazon VPC CIDR (for VPC endpoints) AND to internet (for Cognito JWKS)
- DNS (53): Only to Amazon VPC CIDR (for name resolution)
- Port 25 (SMTP): Explicitly blocked to prevent email abuse
- All other outbound traffic: Blocked

**NAT Gateway:**

- Required for Cognito JWT validation (Cognito has no VPC endpoint)
- VPC endpoints reduce NAT Gateway data transfer for other services
- Cost: ~$32/month

### 3. VPC Endpoints (PrivateLink)

The following VPC endpoints are configured to keep traffic within AWS network:

**Gateway Endpoints (Free):**

- S3: For customer codebase artifacts

**Interface Endpoints (~$14/month each for 2 AZs):**

- Amazon Bedrock Runtime: For AI API calls
- CloudWatch Logs: For application logging
- ECR API: For pulling container images
- ECR Docker: For pulling container layers

**Total VPC Endpoint Cost:** ~$56/month for 2 AZs

### 4. Amazon VPC Flow Logs

Amazon VPC Flow Logs are enabled to CloudWatch Logs for:

- Network traffic monitoring
- Security incident investigation
- Compliance auditing

## Security Benefits

1. **Defense in Depth**: Multiple layers of network controls
2. **Least Privilege**: Only business-justified network paths allowed
3. **Data Exfiltration Prevention**: No internet egress from ECS tasks
4. **Lateral Movement Prevention**: Restricted communication between components
5. **Email Abuse Prevention**: Port 25 explicitly blocked
6. **Audit Trail**: Amazon VPC Flow Logs capture all network activity

## Compliance

This implementation satisfies the following security requirements:

- ✅ Restrict inbound network access to business-justified use cases
- ✅ Restrict outbound network access to business-justified use cases
- ✅ Use VPC endpoints when possible to restrict egress traffic
- ✅ Block SMTP port 25 to prevent email abuse
- ✅ Use Amazon VPC Flow Logs to monitor network traffic
- ✅ Implement least privilege network access controls

## Verification

### Manual Verification

1. **Review Security Groups:**

   ```bash
   aws ec2 describe-security-groups \
     --filters "Name=tag:aws:cloudformation:stack-name,Values=<stack-name>" \
     --query 'SecurityGroups[*].[GroupId,GroupName,IpPermissions,IpPermissionsEgress]'
   ```

2. **Verify VPC Endpoints:**

   ```bash
   aws ec2 describe-vpc-endpoints \
     --filters "Name=vpc-id,Values=<vpc-id>" \
     --query 'VpcEndpoints[*].[VpcEndpointId,ServiceName,State]'
   ```

3. **Check Amazon VPC Flow Logs:**
   ```bash
   aws ec2 describe-flow-logs \
     --filter "Name=resource-id,Values=<vpc-id>"
   ```

### Testing

1. **Test Outbound Connectivity:**
   - ECS tasks should be able to call Amazon Bedrock API
   - ECS tasks should be able to write to CloudWatch Logs
   - ECS tasks should be able to read from S3
   - ECS tasks should NOT be able to reach internet

2. **Test Inbound Connectivity:**
   - CloudFront URL should be accessible
   - Direct ALB URL should NOT be accessible from internet
   - Only CloudFront can reach ALB

## Cost Analysis

**Configuration:**

- NAT Gateway: $32.40/month (required for Cognito)
- S3 Gateway Endpoint: $0
- Amazon Bedrock Interface Endpoint: $14.40/month (2 AZs)
- CloudWatch Logs Interface Endpoint: $14.40/month (2 AZs)
- ECR API Interface Endpoint: $14.40/month (2 AZs)
- ECR Docker Interface Endpoint: $14.40/month (2 AZs)
- **Total: ~$90/month**

**Savings from VPC Endpoints:**

- Reduced NAT Gateway data transfer costs (Amazon Bedrock, S3, CloudWatch, ECR traffic stays in AWS network)
- Estimated savings: $10-20/month in data transfer

**Net Cost vs No VPC Endpoints:**

- Without VPC endpoints: ~$35/month (NAT Gateway + data transfer)
- With VPC endpoints: ~$90/month
- **Net increase: ~$55/month** for improved security and reduced data transfer

## Troubleshooting

### ECS Tasks Can't Pull Images

**Symptom:** Tasks fail to start with "CannotPullContainerError"

**Solution:** Verify ECR VPC endpoints are configured:

- ECR API endpoint
- ECR Docker endpoint
- S3 Gateway endpoint (for image layers)

### ECS Tasks Can't Call Amazon Bedrock

**Symptom:** Amazon Bedrock API calls timeout or fail

**Solution:** Verify Amazon Bedrock Runtime VPC endpoint is configured with private DNS enabled

### ECS Tasks Can't Write Logs

**Symptom:** No logs appearing in CloudWatch Logs

**Solution:** Verify CloudWatch Logs VPC endpoint is configured with private DNS enabled

## References

- [AWS VPC Endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html)
- [AWS Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html)
- [Amazon VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)
- [Amazon Bedrock VPC Endpoints](https://docs.aws.amazon.com/bedrock/latest/userguide/vpc-interface-endpoints.html)
