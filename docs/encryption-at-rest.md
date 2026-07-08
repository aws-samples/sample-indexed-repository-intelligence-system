<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Encryption at Rest

## Overview

IRIS supports encryption at rest for customer content (codebase artifacts) stored in S3 buckets. This document explains how to configure encryption using customer managed keys with AWS Key Management Service (AWS KMS).

## Customer Content Storage

Customer content in IRIS consists of:

- Source code files uploaded to S3
- Generated file summaries and representations
- Codebase metadata

All customer content is stored in the S3 bucket you provide during deployment.

## Encryption Requirements

### S3 Bucket Encryption

**You must configure your S3 bucket with encryption at rest.** IRIS supports two encryption options:

#### Option 1: AWS-Owned Keys (Default)

If you don't specify a KMS key, your S3 bucket should use its default encryption settings (SSE-S3 or SSE-KMS with AWS-managed keys).

#### Option 2: Customer Managed Keys

For enhanced control and compliance requirements, you can encrypt your S3 bucket using a customer managed AWS KMS key.

**Benefits of using customer managed keys:**

- Full control over key policies and access
- Audit trail of all encryption/decryption operations via CloudTrail
- Ability to disable or delete keys
- Support for compliance requirements (FedRAMP, HIPAA, PCI-DSS, etc.)

## Configuration

### Step 1: Create or Use Existing AWS KMS Key

Create a customer managed key in AWS KMS:

```bash
aws kms create-key \
  --description "IRIS S3 encryption key" \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS
```

Note the key ARN from the output (format: `arn:aws:kms:region:account-id:key/key-id`).

### Step 2: Configure S3 Bucket Encryption

Enable default encryption on your S3 bucket using your customer managed AWS KMS key:

```bash
aws s3api put-bucket-encryption \
  --bucket your-bucket-name \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "arn:aws:kms:region:account-id:key/key-id"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

**Note:** `BucketKeyEnabled: true` reduces AWS KMS API costs by using bucket-level keys.

### Step 3: Update Deployment Configuration

Edit `infra/config.yaml` and add your AWS KMS key ARN:

```yaml
codebase_artifacts:
  bucket: "your-bucket-name"
  prefix: ""
  kms_key_arn: "arn:aws:kms:region:account-id:key/key-id"
```

### Step 4: Update AWS KMS Key Policy

Your AWS KMS key policy must allow the ECS task role to decrypt objects. Add this statement to your key policy:

```json
{
  "Sid": "AllowIrisDecrypt",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::account-id:role/IrisStack-TaskRole*"
  },
  "Action": ["kms:Decrypt", "kms:DescribeKey"],
  "Resource": "*"
}
```

**Note:** Replace `account-id` with your AWS account ID. The role name includes a CloudFormation-generated suffix.

### Step 5: Deploy

Deploy the stack with the updated configuration:

```bash
cd infra
cdk deploy
```

## IAM Permissions

When you specify a `kms_key_arn` in the configuration, the ECS task role automatically receives these permissions:

- `kms:Decrypt` - Decrypt S3 objects encrypted with your customer managed AWS KMS key
- `kms:DescribeKey` - Get key metadata

These permissions are scoped to only the AWS KMS key you specify.

## Service Data Encryption

The following service data is encrypted using AWS-owned keys (not customer content):

- **Amazon CloudWatch Logs** - Application logs (encrypted by default)
- **Application Load Balancer Access Logs** - HTTP request metadata (encrypted by default)
- **Amazon CloudFront Access Logs** - CDN request metadata (encrypted by default)
- **Amazon VPC Flow Logs** - Network traffic metadata (encrypted by default)

These do not contain customer content and do not require customer managed AWS KMS key configuration.

## Compliance

Using customer managed AWS KMS keys provides features that can support your compliance programs for standards such as:

- **FedRAMP** - Federal Risk and Authorization Management Program
- **HIPAA** - Health Insurance Portability and Accountability Act
- **PCI-DSS** - Payment Card Industry Data Security Standard
- **GDPR** - General Data Protection Regulation
- **SOC 2** - Service Organization Control 2

Customers are responsible for determining whether their use of AWS services meets applicable compliance requirements.

**Note:** For FedRAMP workloads, customers must use SSE-KMS (not SSE-S3), as S3 default encryption is not FIPS-compliant.

## Verification

### Verify S3 Bucket Encryption

```bash
aws s3api get-bucket-encryption --bucket your-bucket-name
```

### Verify AWS KMS Key Permissions

```bash
aws kms describe-key --key-id your-key-id
aws kms get-key-policy --key-id your-key-id --policy-name default
```

### Monitor AWS KMS Usage

All AWS KMS operations are logged to CloudTrail. You can monitor:

- Who accessed the key
- When decryption operations occurred
- Which resources were decrypted

## Troubleshooting

### Error: Access Denied when reading S3 objects

**Cause:** ECS task role doesn't have permission to use the AWS KMS key.

**Solution:** Update your AWS KMS key policy to allow the ECS task role (see Step 4 above).

### Error: AWS KMS key not found

**Cause:** The AWS KMS key ARN in `config.yaml` is incorrect or the key was deleted.

**Solution:** Verify the key exists and the ARN is correct:

```bash
aws kms describe-key --key-id your-key-id
```

### High AWS KMS API costs

**Cause:** Each S3 object decryption calls AWS KMS API.

**Solution:** Enable S3 Bucket Keys to reduce AWS KMS requests:

```bash
aws s3api put-bucket-encryption \
  --bucket your-bucket-name \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "your-key-arn"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

## Key Rotation

AWS KMS automatically rotates customer managed keys annually. You don't need to update your configuration when keys are rotated.

To manually rotate a key:

```bash
aws kms enable-key-rotation --key-id your-key-id
```

## References

- [AWS KMS Documentation](https://docs.aws.amazon.com/kms/)
- [S3 Encryption Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html)
- [AWS Digital Sovereignty Pledge](https://aws.amazon.com/compliance/digital-sovereignty/)
- [KMS Best Practices](https://docs.aws.amazon.com/kms/latest/developerguide/best-practices.html)
