# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json


def handler(event, context):
    """
    Cognito Pre-signup Lambda trigger to validate email domains.
    This function is called before a user is allowed to sign up.
    """
    print(f"Pre-signup event: {json.dumps(event)}")

    # Get the email from the event
    email = event["request"]["userAttributes"].get("email", "").lower()

    # Get allowed domains from environment variable (set by CDK)
    import os

    allowed_domains_str = os.environ.get("ALLOWED_DOMAINS", "amazon.com")
    allowed_domains = [domain.strip() for domain in allowed_domains_str.split(",")]

    print(f"Validating email: {email}")
    print(f"Allowed domains: {allowed_domains}")

    # Extract domain from email
    if "@" in email:
        domain = email.split("@")[1]

        if domain not in allowed_domains:
            error_msg = f"Email domain '{domain}' is not allowed. Allowed domains: {', '.join(allowed_domains)}"
            print(f"Validation failed: {error_msg}")
            raise Exception(error_msg)
    else:
        error_msg = "Invalid email format"
        print(f"Validation failed: {error_msg}")
        raise Exception(error_msg)

    # If we get here, the email domain is allowed
    print(f"Validation successful for email: {email}")
    return event
