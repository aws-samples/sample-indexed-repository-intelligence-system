<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# User Management Guide

This guide provides detailed instructions for creating and managing user accounts in IRIS using Amazon Cognito User Pool.

## Table of Contents

- [Overview](#overview)
- [Accessing Cognito User Pool](#accessing-cognito-user-pool)
- [User Creation Methods](#user-creation-methods)
- [User Management Operations](#user-management-operations)
- [Troubleshooting](#troubleshooting)

## Overview

IRIS uses Amazon Cognito for user authentication and management. The system supports two sign-in methods:

- **Email-based sign-in**: Users can sign in using their email address
- **Username-based sign-in**: Users can sign in using a custom username

Both methods require email verification during user creation via the AWS console.

## Accessing Cognito User Pool

### Method 1: Via CloudFormation Console

1. **Navigate to CloudFormation Console**:
   - Go to AWS Console → CloudFormation
   - Select the region where you deployed the stack

2. **Find Your Stack**:
   - Look for your deployed stack (default name: `IrisStandalone`)
   - Click on the stack name

3. **Access Resources**:
   - Click the "Resources" tab
   - Search for "UserPool" or filter by "AWS::Cognito::UserPool"
   - Click on the Physical ID link to open the Cognito User Pool

### Method 2: Direct Cognito Console Access

1. **Navigate to Cognito Console**:
   - Go to AWS Console → Cognito
   - Select "User pools"

2. **Find Your User Pool**:
   - Look for "IrisUserPool"
   - Click on the user pool name

## User Creation Methods

### Method 1: Email-Based User Creation

This method creates a user account where the email address serves as both the identifier and username.

#### Steps:

1. **Access User Pool**:
   - Navigate to your Cognito User Pool (see [Accessing Cognito User Pool](#accessing-cognito-user-pool))

2. **Create New User**:
   - Click "Users" in the left sidebar
   - Click "Create user" button

3. **Configure User Settings**:
   - **Invitation message**: Select "Don't send an invitation"
   - **User name**: Enter the user's email address (e.g., `user@example.com`)
   - **Email address**: Enter the same email address
   - **Mark email address as verified**: ✅ **CRITICAL: Check this box**
   - **Temporary password**: Select "Set a password"
   - **Password**: Enter a temporary password (must meet password policy requirements)

4. **Complete Creation**:
   - Click "Create user"
   - User can now login using their email address and temporary password

#### Example Configuration:

```
User name: user@example.com
Email address: user@example.com
Email verified: ✅ YES
Temporary password: TempPass123!
```

### Method 2: Username-Based User Creation

This method creates a user account with a custom username separate from the email address.

#### Steps:

1. **Access User Pool**:
   - Navigate to your Cognito User Pool (see [Accessing Cognito User Pool](#accessing-cognito-user-pool))

2. **Create New User**:
   - Click "Users" in the left sidebar
   - Click "Create user" button

3. **Configure User Settings**:
   - **Invitation message**: Select "Don't send an invitation"
   - **User name**: Enter a custom username (e.g., `johndoe`, `john.doe`, `jdoe`)
   - **Email address**: Enter the user's email address
   - **Mark email address as verified**: ✅ **CRITICAL: Check this box**
   - **Temporary password**: Select "Set a password"
   - **Password**: Enter a temporary password (must meet password policy requirements)

4. **Complete Creation**:
   - Click "Create user"
   - User can now login using their username and temporary password

5. **Important - First Login Required**:
   - ⚠️ **CRITICAL**: The password reset screen only appears on the first login attempt
   - **Administrator must login first** with the temporary password to set a permanent password
   - **Only then share the permanent credentials** with the actual user
   - If you skip this step, the user won't be able to reset their password

#### Example Configuration:

```
User name: johndoe
Email address: user@example.com
Email verified: ✅ YES
Temporary password: TempPass123!
```

**⚠️ Important Workflow for Username-Based Users:**

1. Administrator creates user with temporary password
2. **Administrator logs in first** using username and temporary password
3. Administrator sets permanent password during first login
4. Administrator shares username and permanent password with actual user

### Password Policy Requirements

All temporary passwords must meet the following requirements:

- **Minimum length**: 8 characters
- **Lowercase letters**: At least one (a-z)
- **Uppercase letters**: At least one (A-Z)
- **Numbers**: At least one (0-9)
- **Symbols**: At least one (!@#$%^&\*)

#### Valid Password Examples:

- `TempPass123!`
- `Welcome2024#`
- `MyPass456$`

## User Management Operations

### Viewing User Details

1. **Access User List**:
   - Navigate to Cognito User Pool → Users

2. **View User Information**:
   - Click on any username to view detailed information
   - Check user status, attributes, and sign-in history

### Resetting User Passwords

1. **Select User**:
   - Navigate to Users → Click on username

2. **Reset Password**:
   - Click "Actions" → "Reset password"
   - Choose to send reset link or set new temporary password
   - If setting temporary password, ensure it meets policy requirements

### Enabling/Disabling Users

1. **Select User**:
   - Navigate to Users → Click on username

2. **Change Status**:
   - Click "Actions" → "Disable user" or "Enable user"
   - Disabled users cannot sign in until re-enabled

### Deleting Users

1. **Select User**:
   - Navigate to Users → Click on username

2. **Delete User**:
   - Click "Actions" → "Delete user"
   - Confirm deletion (this action cannot be undone)

## User Login Process

### For Email-Based Users

1. **Navigate to Application**:
   - Go to the CloudFront URL provided after deployment

2. **Sign In**:
   - Enter email address in the username field
   - Enter password
   - Click "Sign In"

3. **First Login**:
   - If using temporary password, user will be prompted to set a new permanent password
   - New password must meet the password policy requirements

### For Username-Based Users

**⚠️ Important**: For username-based accounts, the administrator must complete the first login to set the permanent password before sharing credentials.

1. **Administrator First Login**:
   - Navigate to the CloudFront URL
   - Enter username and temporary password
   - Set a permanent password when prompted
   - Note down the permanent password

2. **Share Credentials with User**:
   - Provide the username and permanent password to the actual user
   - User can now sign in normally

3. **User Subsequent Logins**:
   - Enter username and permanent password
   - No additional password reset required

## Troubleshooting

### Common Issues

#### 1. Email Domain Not Allowed

**Note**: This error only occurs if self-signup is enabled (which is disabled by default). When creating users via console, there are no domain restrictions.

#### 2. Email Not Verified

**Error**: User cannot sign in or receives verification errors

**Solution**:

- Ensure "Mark email address as verified" was checked during user creation
- If not checked, edit the user and manually verify the email address:
  1. Go to Users → Select user → Attributes tab
  2. Find "email_verified" attribute
  3. Change value to "true"

#### 3. Password Policy Violations

**Error**: "Password does not meet requirements"

**Solution**:

- Ensure password meets all policy requirements:
  - At least 8 characters
  - Contains uppercase, lowercase, numbers, and symbols
- Use passwords like `TempPass123!` or `Welcome2024#`

#### 4. User Cannot Sign In

**Possible Causes and Solutions**:

1. **Wrong Credentials**:
   - Verify username/email and password are correct
   - Check if user is using email vs. username correctly

2. **Password Reset Not Completed (Username-based users)**:
   - **For username-based accounts**: Administrator must complete first login
   - The password reset screen only appears on the first login attempt
   - If skipped, user cannot reset password - administrator must reset via console

3. **User Disabled**:
   - Check user status in Cognito console
   - Enable user if disabled

4. **Email Not Verified**:
   - Verify email address is marked as verified in user attributes

5. **Account Locked**:
   - Check if account is locked due to failed login attempts
   - Wait for lockout period to expire or reset password

#### 5. Self-Signup Issues

**Note**: Self-signup is disabled by default. Users must be created via the AWS console by administrators.

### Checking User Pool Configuration

To verify your User Pool configuration:

1. **Navigate to User Pool**:
   - Go to Cognito Console → User pools → IrisUserPool

2. **Check Sign-in Options**:
   - Go to "Sign-in experience" tab
   - Verify both "Email" and "Username" are enabled under "Cognito user pool sign-in options"

3. **Check Attributes**:
   - Go to "Sign-up experience" tab
   - Verify "Email" is listed under "Required attributes"
   - Verify "Email" is listed under "Attributes to verify"

### Getting Help

If you encounter issues not covered in this guide:

1. **Check CloudWatch Logs**:
   - Look for authentication-related errors in ECS task logs
   - Check Lambda function logs if self-signup is enabled (disabled by default)

2. **Verify Configuration**:
   - Ensure CloudFormation stack deployed successfully
   - Check that Cognito User Pool was created properly

3. **Test with Different Users**:
   - Try creating users with different email addresses
   - Test both email-based and username-based sign-in methods

## Related Documentation

- [Deployment Guide](deployment-guide.md) - Initial setup and deployment
- [Architecture Overview](architecture.md) - System architecture and Cognito integration
- [Development Guide](dev-guide.md) - Development and testing procedures
