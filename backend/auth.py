# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
JWT Authentication for AWS Cognito
"""

import os
import logging
import time
import requests
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
import jwt
from jwt.exceptions import InvalidTokenError

log = logging.getLogger(__name__)


class CognitoJWTAuth:
    """AWS Cognito JWT Authentication handler"""

    _JWKS_TTL = 300  # refresh JWKS at most every 5 minutes
    _JWKS_MIN_INTERVAL = 60  # throttle unknown-kid refreshes to once per minute

    def __init__(self):
        # Get Cognito configuration from environment variables
        self.region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.user_pool_id = os.getenv("USER_POOL_ID", "")
        self.app_client_id = os.getenv("USER_POOL_CLIENT_ID", "")
        self._jwks_fetched_at: float = 0.0
        self._jwks_last_refresh: float = 0.0

        # ALLOW_ANONYMOUS must be explicitly set to "true" to permit unauthenticated
        # access (e.g. local development). Without this, missing Cognito config causes
        # all requests to be rejected (fail-closed).
        self.allow_anonymous = os.getenv("ALLOW_ANONYMOUS", "false").lower() == "true"

        if not self.user_pool_id or not self.app_client_id:
            if self.allow_anonymous:
                log.warning(
                    "Cognito not configured and ALLOW_ANONYMOUS=true — "
                    "anonymous access permitted. Do NOT use this in production."
                )
            else:
                log.warning(
                    "Cognito not configured. All auth requests will be rejected. "
                    "Set ALLOW_ANONYMOUS=true for local development."
                )
            self.enabled = False
            self.jwks = None
        else:
            self.enabled = True
            self.jwks_url = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json"
            self.issuer = (
                f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
            )
            self.jwks = self._get_jwks()
            log.info(f"Cognito JWT auth enabled for region {self.region}")

    def _get_jwks(self) -> Optional[Dict]:
        """Fetch JWKS from Cognito and record fetch timestamp."""
        try:
            response = requests.get(self.jwks_url, timeout=10)
            response.raise_for_status()
            self._jwks_fetched_at = time.time()
            return response.json()
        except Exception as e:
            log.error(f"Failed to fetch JWKS: {e}")
            return None

    def _get_signing_key(self, kid: str):
        """Get signing key from JWKS, refreshing on TTL expiry or cache miss."""
        now = time.time()

        # Proactive TTL refresh so normal verification doesn't trigger network calls
        if self.jwks and (now - self._jwks_fetched_at) > self._JWKS_TTL:
            log.info("JWKS TTL expired, refreshing proactively...")
            self.jwks = self._get_jwks()

        if not self.jwks:
            return None

        for key in self.jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)

        # Key not found — throttle refresh attempts to prevent DoS via crafted kid values
        if (now - self._jwks_last_refresh) < self._JWKS_MIN_INTERVAL:
            log.warning(
                f"Unknown kid {kid!r} but refresh throttled — try again shortly"
            )
            return None

        log.info(f"Key ID {kid!r} not in cached JWKS, refreshing...")
        self._jwks_last_refresh = now
        self.jwks = self._get_jwks()
        if not self.jwks:
            return None

        for key in self.jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)

        return None

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify JWT token with AWS Cognito

        Args:
            token: JWT token string

        Returns:
            Dict with user claims if valid, None if invalid
        """
        if not self.enabled:
            if self.allow_anonymous:
                log.debug("Anonymous access granted (ALLOW_ANONYMOUS=true)")
                return {"sub": "anonymous", "email": "anonymous@local"}
            else:
                log.warning(
                    "Token verification rejected — Cognito not configured "
                    "and ALLOW_ANONYMOUS is not enabled"
                )
                return None

        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]

            # Get the key ID from token header
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            if not kid:
                log.error("No key ID found in token header")
                return None

            # Get the signing key
            signing_key = self._get_signing_key(kid)
            if not signing_key:
                log.error(f"No signing key found for kid: {kid}")
                return None

            # Verify and decode token
            verified_claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.app_client_id,
                issuer=self.issuer,
                options={"verify_exp": True},
            )

            # Validate token_use claim for Cognito (should be 'access' or 'id')
            token_use = verified_claims.get("token_use")
            if token_use not in ["access", "id"]:
                log.error(f"Invalid token_use: {token_use}")
                return None

            log.info(
                f"JWT verified for user: {verified_claims.get('email', 'unknown')}"
            )
            return verified_claims

        except InvalidTokenError as e:
            log.error(f"JWT verification failed: {str(e)}")
            return None
        except Exception as e:
            log.error(f"Unexpected error during JWT verification: {str(e)}")
            return None

    def get_user_from_token(self, token: str) -> Optional[Dict[str, str]]:
        """
        Extract user information from JWT token

        Returns:
            Dict with user info or None if invalid
        """
        claims = self.verify_token(token)
        if not claims:
            return None

        return {
            "user_id": claims.get("sub", ""),
            "email": claims.get("email", ""),
            "username": claims.get("cognito:username", claims.get("email", "")),
        }


# Global instance
cognito_auth = CognitoJWTAuth()


def authenticate_websocket_token(token: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Authenticate WebSocket connection token

    Args:
        token: JWT token from WebSocket headers

    Returns:
        User info dict if authenticated, None if not
    """
    if not token:
        return None

    return cognito_auth.get_user_from_token(token)


def require_auth(token: Optional[str]) -> Dict[str, str]:
    """
    Require authentication - raises HTTPException if not authenticated

    Args:
        token: JWT token

    Returns:
        User info dict

    Raises:
        HTTPException: If authentication fails
    """
    user = authenticate_websocket_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )
    return user
