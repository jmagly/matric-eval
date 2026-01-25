# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email the maintainers directly or use GitHub's private vulnerability reporting
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a detailed response
within 7 days, including next steps for handling the report.

## Security Considerations

This project executes code as part of evaluation benchmarks. The evaluation
framework includes sandboxing with:

- Execution timeouts
- Memory limits
- No network access during code execution

When running evaluations, use appropriate isolation (containers, VMs) for
untrusted model outputs.
