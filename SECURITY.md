# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.0.x   | Yes       |

## Reporting a Vulnerability

Please report security vulnerabilities via email:

**james@think.dev**

Do **not** open a public GitHub issue for security concerns.

### What to expect

- Acknowledgment within 48 hours.
- A fix or mitigation for critical issues within 7 days.
- Credit in the changelog (unless you prefer anonymity).

## Security Considerations

membase is a thin wrapper around `huggingface_hub`. It does not
implement its own authentication, encryption, or network protocols.
Security-relevant behavior is inherited from the underlying SDK.

Key points:

- **API tokens.** membase discovers HF tokens from the environment
  (`HF_TOKEN`) or stored credentials. Never commit tokens to version
  control.
- **Workspace visibility.** Buckets can be public or private. Ensure
  you set `private=True` (the default) for sensitive workspaces.
- **File content.** membase reads and writes files to remote storage.
  Be mindful of what data your agents write to shared workspaces.
