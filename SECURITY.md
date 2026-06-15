# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ Yes    |
| 0.1.x   | ❌ No     |

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please **do not** open a public
GitHub issue. Instead:

1. **Email** the maintainer directly at the email address associated with the
   [Nandi-Pura GitHub account](https://github.com/Nandi-Pura).
2. Include in your report:
   - A description of the vulnerability
   - Steps to reproduce (proof-of-concept, if available)
   - Potential impact
   - Any suggested mitigations

You can expect:
- **Acknowledgement** within 3 business days
- **Status update** within 10 business days
- **Public disclosure** coordinated with you after a fix is released

---

## Security Considerations for Operators

### Secrets Management

- Never commit your `.env` file or any file containing `CLEARPASS_CLIENT_SECRET` to version control.
- Use environment variables or a secrets manager (HashiCorp Vault, AWS Secrets Manager, etc.)
  rather than `.env` files in production deployments.
- Rotate your ClearPass API client secret periodically.

### TLS Verification

- Always keep `CLEARPASS_VERIFY_SSL=true` in production.
- If you use a private CA, mount the CA bundle into the container and set `SSL_CERT_FILE`
  rather than disabling verification.

### Network Exposure

- When using the SSE transport (`--transport sse`), place the server behind a reverse proxy
  (nginx, Caddy) with TLS termination and authentication if exposing it beyond `localhost`.
- The default SSE bind address is `127.0.0.1` (loopback only). Change to `0.0.0.0` only
  in controlled environments.

### Principle of Least Privilege

- Create a dedicated ClearPass API client for this integration with the minimum required
  Operator Profile permissions.
- Use `CLEARPASS_READ_ONLY=true` for monitoring-only deployments.

---

## Not a ClearPass Security Issue

If you have found a security issue in Aruba ClearPass Policy Manager itself (not in this
MCP server), please report it through the official
[HPE Security Vulnerability Disclosure Process](https://www.hpe.com/h20565/v2/getpdf.aspx/hpe-security-vulnerability-disclosure.pdf).
