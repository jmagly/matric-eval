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

This project executes model-generated code as part of evaluation benchmarks.
The basic Python code scorer uses a local subprocess with a timeout and captured
output. It does not enforce filesystem isolation, network denial, or memory
limits. An inference server such as Ollama does not sandbox that subprocess.

Run untrusted model outputs inside an appropriately configured container or VM.
Some tasks use separate sandbox services or official external runners; inspect
the selected task's requirements rather than assuming every scorer uses the same
isolation. See the [execution boundaries](docs/architecture/overview.md#execution-boundaries)
and [benchmark protocol index](docs/README.md#benchmark-protocols).
