<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# Security Headers Implementation

This document describes how IRIS applies security HTTP headers to protect the web
application against common attacks. The React app is served as static content from a
private Amazon S3 bucket through Amazon CloudFront; chat/API traffic goes directly to the
Amazon Bedrock AgentCore Runtime data-plane endpoint (which does not serve HTML to the
browser). Security headers therefore apply to the static frontend responses delivered by
CloudFront.

## Required Security Headers

As per AWS security best practices, IRIS relies on the following headers for the web app:

1. **X-Frame-Options** — mitigates clickjacking by restricting framing of the page
2. **X-Content-Type-Options: nosniff** — prevents MIME type sniffing
3. **Strict-Transport-Security** — enforces HTTPS on subsequent requests
4. **Referrer-Policy** — limits referrer information sent to other origins
5. **Content-Security-Policy** — mitigates XSS (see [Content Security Policy](#content-security-policy-csp))

## Implementation Layers

### 1. Amazon CloudFront (Primary Layer)

**File:** `infra/stack.py`

The CloudFront distribution attaches the AWS-managed
`ResponseHeadersPolicy.SECURITY_HEADERS` policy to its default behavior:

```python
distribution = cloudfront.Distribution(
    self,
    "FrontendDistribution",
    default_behavior=cloudfront.BehaviorOptions(
        origin=s3_origin,  # private S3 bucket via Origin Access Control (OAC)
        viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        ...
    ),
    minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
    ...
)
```

The AWS-managed `SecurityHeadersPolicy` adds the following headers to every response
CloudFront sends to viewers:

| Header                      | Value                              |
| --------------------------- | ---------------------------------- |
| `Strict-Transport-Security` | `max-age=31536000`                 |
| `X-Content-Type-Options`    | `nosniff`                          |
| `X-Frame-Options`           | `SAMEORIGIN`                       |
| `X-XSS-Protection`          | `1; mode=block`                    |
| `Referrer-Policy`           | `strict-origin-when-cross-origin`  |

**Benefits:**

- Headers applied globally at edge locations, on every static-asset response.
- Consistent, AWS-maintained policy — no custom header policy to maintain.
- No application code changes needed for baseline protection.

> **Note:** the managed `SecurityHeadersPolicy` does not set a `Content-Security-Policy`.
> IRIS's XSS defense for the SPA is enforced in the React application itself (see below),
> and a CSP is applied for local development by the static file server configuration.

### 2. React Application (XSS Defenses)

Because chat responses are AI-generated and may contain arbitrary Markdown, the strongest
XSS protections live in the rendering pipeline rather than in a header:

- **`frontend/src/components/MessageBubble.jsx`** — ReactMarkdown is configured with
  `skipHtml={true}`, so raw HTML embedded in AI responses is never rendered. `rehype-raw`
  is intentionally not used.
- **`frontend/src/components/MermaidChart.jsx`** — Mermaid is initialized with
  `securityLevel: "strict"` (no raw HTML, no `click` JavaScript handlers), and the rendered
  SVG is passed through DOMPurify before it is inserted into the DOM.

These controls prevent script execution from untrusted response content regardless of the
transport headers.

### 3. Static File Server (Local Development)

**File:** `frontend/serve.json`

For local runs that serve the built app with the `serve` package, `serve.json` adds
security headers to static files, including a `Content-Security-Policy` and
`Cache-Control`:

```json
{
  "headers": [
    {
      "source": "**/*",
      "headers": [
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains" },
        { "key": "Cache-Control", "value": "no-store, no-cache" },
        { "key": "Content-Security-Policy", "value": "default-src 'self'; ..." }
      ]
    }
  ]
}
```

**Benefits:**

- Header parity for local development where CloudFront is not in the path.
- No code changes to the React application.

## Content Security Policy (CSP)

The CSP applied by the local static file server (`frontend/serve.json`) is:

```
default-src 'self';
script-src 'self' 'unsafe-inline' 'unsafe-eval';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
font-src 'self' data:;
connect-src 'self' http://localhost:* ws://localhost:* wss: https:;
frame-ancestors 'none';
```

**Directives:**

- `default-src 'self'` — only load resources from the same origin by default
- `script-src` — allows inline scripts (needed by the React build)
- `style-src` — allows inline styles
- `img-src` — allows images from same origin, data URIs, and HTTPS
- `connect-src` — allows HTTPS connections (to the AgentCore data-plane endpoint) plus
  local dev endpoints
- `frame-ancestors 'none'` — prevents embedding (equivalent to `X-Frame-Options: DENY`)

## HTTPS Enforcement

### Browser to Amazon CloudFront (static frontend)

- **Enforced via:** `viewer_protocol_policy = REDIRECT_TO_HTTPS`
- **TLS version:** TLS 1.2 minimum (`minimum_protocol_version = TLS_V1_2_2021`)
- **Certificate:** CloudFront default certificate (`*.cloudfront.net`)

### Amazon CloudFront to the Amazon S3 origin

- **Origin access:** Origin Access Control (OAC); the S3 bucket is private
  (`BlockPublicAccess.BLOCK_ALL`) and reachable only through CloudFront.
- **Encryption:** CloudFront-to-S3 traffic is served over HTTPS.

### Browser to Amazon Bedrock AgentCore Runtime (chat/API)

- The browser calls `https://bedrock-agentcore.{region}.amazonaws.com/...` directly over
  TLS. This is a separate AWS-managed endpoint and is not fronted by CloudFront.

### HSTS Header

The managed policy sets `Strict-Transport-Security: max-age=31536000`, instructing browsers
to use HTTPS for future requests to the CloudFront domain.

## Verification

### Manual Testing

1. **Using browser DevTools:**

   ```
   1. Open the CloudFront URL in Chrome/Firefox
   2. Open DevTools (F12) → Network tab
   3. Refresh the page and select any request
   4. Check the Response Headers section
   ```

2. **Using curl:**

   ```bash
   curl -I https://your-cloudfront-domain.cloudfront.net
   ```

3. **Using security scanning tools:**
   - [Mozilla Observatory](https://observatory.mozilla.org/)
   - [Security Headers](https://securityheaders.com/)
   - OWASP ZAP

### Expected Headers (Amazon CloudFront responses)

```
Strict-Transport-Security: max-age=31536000
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

## Deployment

The security headers are applied automatically when the stack is deployed — the managed
`SECURITY_HEADERS` response headers policy is attached to the CloudFront distribution at
creation time. No additional configuration is required.

## Compliance Notes

- ✅ Baseline security headers applied at the edge via the AWS-managed policy
- ✅ HTTPS enforced (`REDIRECT_TO_HTTPS`) with TLS 1.2 minimum
- ✅ XSS mitigated in the React rendering pipeline (`skipHtml`, DOMPurify, Mermaid strict)
- ✅ CSP applied for local development via the static file server
- ⚠️ The managed policy sets `X-Frame-Options: SAMEORIGIN` and does not include a CSP;
  operators who need `DENY` or an edge CSP can attach a custom `ResponseHeadersPolicy`.

## References

- [AWS Security Best Practices](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/)
- [CloudFront managed response headers policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-response-headers-policies.html)
- [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [MDN Web Security](https://developer.mozilla.org/en-US/docs/Web/Security)
