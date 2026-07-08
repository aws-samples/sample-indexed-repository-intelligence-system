<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Security Headers Implementation

This document describes the implementation of security HTTP headers for the IRIS application to protect against common web application attacks.

## Required Security Headers

As per AWS security best practices, the following headers are implemented:

1. **X-Frame-Options: DENY** - Prevents clickjacking by disallowing the page to be embedded in frames
2. **X-Content-Type-Options: nosniff** - Prevents MIME type sniffing
3. **Strict-Transport-Security: max-age=47304000; includeSubDomains** - Enforces HTTPS for 18 months
4. **Cache-Control: no-store, no-cache** - Prevents caching of sensitive data
5. **Content-Security-Policy** - Mitigates XSS attacks (replaces deprecated X-XSS-Protection)

## Implementation Layers

### 1. CloudFront (Primary Layer)

**File:** `infra/stack.py`

CloudFront applies security headers at the edge using a custom `ResponseHeadersPolicy`:

```python
security_headers_policy = cloudfront.ResponseHeadersPolicy(
    self,
    "SecurityHeadersPolicy",
    security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
        content_type_options=...,
        frame_options=...,
        strict_transport_security=...,
        content_security_policy=...,
    ),
    custom_headers_behavior=cloudfront.ResponseCustomHeadersBehavior(
        custom_headers=[
            cloudfront.ResponseCustomHeader(
                header="Cache-Control",
                value="no-store, no-cache",
                override=True
            ),
        ]
    ),
)
```

**Benefits:**

- Headers applied globally at edge locations
- Consistent security posture across all responses
- No application code changes needed for basic protection

### 2. Backend (FastAPI)

**File:** `backend/websocket_server.py`

FastAPI middleware adds security headers to all HTTP responses:

```python
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=47304000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store, no-cache"
    response.headers["Content-Security-Policy"] = "..."
    return response
```

**Benefits:**

- Defense in depth - headers present even if CloudFront is bypassed
- Applies to WebSocket upgrade responses
- Applies to API endpoints (/health, /config, etc.)

### 3. Frontend (Static File Server)

**Files:**

- `frontend/serve.json` - Configuration file
- `frontend/startup-cloud.sh` - Updated to use configuration
- `frontend/Dockerfile` - Copies configuration file

The `serve` package uses `serve.json` to add headers to static files:

```json
{
  "headers": [
    {
      "source": "**/*",
      "headers": [
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        ...
      ]
    }
  ]
}
```

**Benefits:**

- Headers on HTML, JS, CSS, and other static assets
- Works in local development and production
- No code changes to React application

## Content Security Policy (CSP)

The CSP header is configured to allow the application to function while providing security:

```
default-src 'self';
script-src 'self' 'unsafe-inline' 'unsafe-eval';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
font-src 'self' data:;
connect-src 'self' wss: https:;
frame-ancestors 'none';
```

**Directives:**

- `default-src 'self'` - Only load resources from same origin by default
- `script-src` - Allows inline scripts (needed for React)
- `style-src` - Allows inline styles (needed for styled components)
- `img-src` - Allows images from same origin, data URIs, and HTTPS
- `connect-src` - Allows WebSocket and HTTPS connections
- `frame-ancestors 'none'` - Prevents embedding (same as X-Frame-Options)

## HTTPS Enforcement

### Client to CloudFront

- **Enforced via:** `viewer_protocol_policy: REDIRECT_TO_HTTPS`
- **TLS Version:** TLS 1.2+ (via `minimum_protocol_version`)
- **Certificate:** CloudFront default certificate (\*.cloudfront.net)

### CloudFront to ALB

- **Protocol:** HTTP only (no TLS)
- **Justification:**
  - No custom domain/certificate available
  - Traffic stays within AWS network
  - End-to-end encryption not required for internal communication
  - Client traffic is encrypted (client → CloudFront)

### HSTS Header

The `Strict-Transport-Security` header ensures browsers only use HTTPS for future requests:

- `max-age=47304000` - 18 months (recommended by AWS)
- `includeSubDomains` - Applies to all subdomains

## Verification

### Manual Testing

1. **Using Browser DevTools:**

   ```
   1. Open CloudFront URL in Chrome/Firefox
   2. Open DevTools (F12) → Network tab
   3. Refresh page and select any request
   4. Check Response Headers section
   ```

2. **Using curl:**

   ```bash
   curl -I https://your-cloudfront-domain.cloudfront.net
   ```

3. **Using security scanning tools:**
   - [Mozilla Observatory](https://observatory.mozilla.org/)
   - [Security Headers](https://securityheaders.com/)
   - OWASP ZAP

### Expected Headers

All responses should include:

```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=47304000; includeSubDomains
Cache-Control: no-store, no-cache
Content-Security-Policy: default-src 'self'; ...
```

## Deployment

The security headers are automatically applied when deploying via CDK:

```bash
cd infra
cdk deploy
```

No additional configuration is required. The headers are applied at:

1. CloudFront distribution creation
2. Backend container startup
3. Frontend container startup

## Compliance Notes

- ✅ X-XSS-Protection header is NOT used (deprecated, replaced by CSP)
- ✅ All required headers are present
- ✅ HSTS includes subdomains and 18-month duration
- ✅ Cache-Control prevents sensitive data caching
- ✅ CSP provides XSS protection
- ⚠️ CloudFront to ALB uses HTTP (acceptable for internal AWS traffic)

## References

- [AWS Security Best Practices](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/)
- [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [MDN Web Security](https://developer.mozilla.org/en-US/docs/Web/Security)
- [CloudFront Response Headers Policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/adding-response-headers.html)
