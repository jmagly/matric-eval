# Security Posture

**Document ID**: SEC-POS-001
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Approved
**Profile**: Production with Baseline Security Posture

## 1. Executive Summary

matric-eval is an internal model evaluation framework for the matric ecosystem. This document defines the security posture appropriate for a **Baseline** security level, which has been intentionally selected as an override from the default Production (Strong) posture.

**Rationale for Baseline Posture**:
- Internal development tool with no external network exposure
- No PII or sensitive user data processed
- No authentication or multi-user access requirements
- Evaluation data consists of public benchmarks (HumanEval, MBPP, GSM8K)
- Code execution occurs within Ollama's sandboxed environment
- Single-developer, single-machine deployment model

## 2. Security Requirements

### 2.1 Applicable Requirements (Baseline)

| Requirement ID | Category | Description | Priority |
|---------------|----------|-------------|----------|
| SEC-001 | Code Execution | Sandboxed execution of model-generated code | P1 - Critical |
| SEC-002 | Input Validation | Validate user inputs to prevent injection | P1 - Critical |
| SEC-003 | Dependency Security | SBOM management and vulnerability scanning | P2 - High |
| SEC-004 | Secrets Management | Environment-based secrets, no hardcoding | P2 - High |
| SEC-005 | Dataset Integrity | Checksum validation for benchmark datasets | P3 - Medium |

### 2.2 Excluded Requirements (Not Applicable)

The following security controls are **intentionally excluded** for Baseline posture:

| Control | Reason for Exclusion |
|---------|---------------------|
| User Authentication | Local CLI tool, no multi-user access |
| Authorization/RBAC | File system permissions sufficient |
| Data Encryption at Rest | No sensitive data stored |
| Data Encryption in Transit | Local-only communication to Ollama |
| Audit Logging | Development tool, no compliance requirements |
| SAST/DAST Scanning | Baseline posture, manual code review sufficient |
| Penetration Testing | Internal tool, not exposed to network |
| Incident Response Playbooks | Deferred until network exposure |
| SOC2/ISO27001 Compliance | No compliance requirements |

## 3. Authentication and Authorization

### 3.1 Authentication

**Requirement**: None required

**Implementation**: matric-eval operates as a local CLI tool. Access control is delegated to the operating system:

```
Access Model:
  User -> File System Permissions -> matric-eval CLI -> Ollama (localhost)
```

**Controls**:
- Execution requires appropriate file system permissions on the installation directory
- Results directory permissions control who can read evaluation outputs
- No API keys or tokens required for core functionality

### 3.2 Authorization

**Requirement**: File system permissions only

**Implementation**:

| Resource | Permission Model |
|----------|-----------------|
| Source code (`src/`) | Read-only for users, write for developers |
| Datasets (`datasets/`) | Read-only after initial download |
| Results (`results/`) | Read-write for evaluation user |
| Configuration (`~/.matric-eval/`) | User-only (700) |
| Lock files (`results/run-*/lock`) | User-only, exclusive access |

**Directory Permission Recommendations**:
```bash
# Installation directory
chmod 755 /path/to/matric-eval

# User configuration
chmod 700 ~/.matric-eval

# Results directory
chmod 755 results/
chmod 644 results/run-*/**.json

# Downloaded datasets (read-only)
chmod 444 datasets/public/**
```

## 4. Data Protection

### 4.1 Data Classification

| Data Type | Classification | Protection Level |
|-----------|---------------|-----------------|
| Public benchmark datasets | Public | None required |
| Model responses | Internal | File system permissions |
| Evaluation scores | Internal | File system permissions |
| Checkpoint state | Internal | File system permissions |
| Ollama API endpoint | Configuration | Environment variables |
| Log files | Internal | File system permissions |

### 4.2 Data Handling

**No Sensitive Data**: matric-eval does not process, store, or transmit:
- Personally Identifiable Information (PII)
- Authentication credentials (except Ollama endpoint)
- Financial or health data
- Proprietary business data

**Data Lifecycle**:
```
1. INPUT:  Public benchmark datasets (HumanEval, MBPP, GSM8K)
2. PROCESS: Model inference via Ollama API (localhost)
3. OUTPUT: Evaluation scores, generated code, performance metrics
4. STORAGE: Local file system (results/ directory)
5. RETENTION: User-controlled, no automatic expiration
```

### 4.3 Encryption

**At Rest**: Not implemented (not required for Baseline posture)
- All data is non-sensitive (public benchmarks, internal development metrics)
- File system encryption (LUKS, FileVault) provides sufficient protection if needed

**In Transit**: Not applicable
- All communication is localhost (CLI to Ollama on 127.0.0.1:11434)
- No external network communication during evaluation

## 5. Dependency Management

### 5.1 SBOM (Software Bill of Materials)

**Implementation**: Maintained via `uv.lock`

```bash
# Generate dependency list
uv pip list --format=freeze > requirements.txt

# Lock file provides complete dependency tree
cat uv.lock
```

**Controls**:
- `uv.lock` committed to version control for reproducibility
- All dependencies pinned to exact versions
- Transitive dependencies tracked and locked

### 5.2 Vulnerability Scanning

**Tools**:
- `pip-audit` for Python vulnerabilities
- `safety` as alternative scanner

**CI/CD Integration**:
```yaml
# GitHub Actions example
security-scan:
  steps:
    - run: uv pip install pip-audit
    - run: pip-audit --strict --desc on
```

**Policy**:
| Severity | Response Time | Action |
|----------|--------------|--------|
| Critical | 24 hours | Immediate patch or removal |
| High | 7 days | Patch in next release |
| Medium | 30 days | Patch when convenient |
| Low | 90 days | Track and monitor |

### 5.3 Dependency Updates

**Cadence**: Monthly security review

**Process**:
1. Run `uv lock --upgrade` to check for updates
2. Run `pip-audit` on updated dependencies
3. Run test suite to verify compatibility
4. Commit updated `uv.lock` if tests pass

**Approved Sources**:
- PyPI (https://pypi.org) - Primary source
- GitHub releases - For pre-release testing only

## 6. Secrets Management

### 6.1 Secret Types

| Secret | Storage | Usage |
|--------|---------|-------|
| `OLLAMA_BASE_URL` | Environment variable | Ollama API endpoint (default: localhost:11434) |
| `MATRIC_EVAL_LOG_LEVEL` | Environment variable | Logging configuration |

### 6.2 Secret Handling Policy

**Prohibited**:
- Hardcoded secrets in source code
- Secrets in committed configuration files
- Secrets in log output
- Secrets in checkpoint files

**Required**:
- All secrets loaded from environment variables
- Secrets redacted in log output (`***REDACTED***`)
- `.gitignore` includes secret file patterns

**.gitignore entries**:
```gitignore
# Secrets and credentials
.env
.env.*
*.env
credentials.*
secrets.*
*.pem
*.key

# Local configuration
.matric-eval/
```

### 6.3 Secret Validation

**Pre-commit Hook** (optional):
```bash
#!/bin/bash
# Check for potential secrets in staged files
if git diff --cached --name-only | xargs grep -l -E "(password|secret|api_key|token)\s*=" 2>/dev/null; then
    echo "ERROR: Potential secret detected in staged files"
    exit 1
fi
```

## 7. Security Testing Requirements

### 7.1 Required Testing (Baseline)

| Test Type | Scope | Frequency |
|-----------|-------|-----------|
| Dependency scanning | All Python dependencies | Every CI run |
| Input fuzzing | CLI arguments, file paths | Pre-release |
| Sandbox validation | Code execution isolation | Pre-release |
| Secret detection | Source code, config files | Pre-commit |

### 7.2 Test Cases

**Input Validation Tests**:
```python
# tests/test_security.py

def test_model_name_injection():
    """Model names with injection attempts are rejected."""
    malicious_names = [
        "../../etc/passwd",
        "model; rm -rf /",
        "model$(whoami)",
        "model`cat /etc/passwd`",
    ]
    for name in malicious_names:
        with pytest.raises(ValidationError):
            validate_model_name(name)

def test_path_traversal_prevention():
    """Output paths cannot escape results directory."""
    malicious_paths = [
        "../../../etc/passwd",
        "/etc/passwd",
        "results/../../../tmp/pwned",
    ]
    for path in malicious_paths:
        with pytest.raises(ValidationError):
            validate_output_path(path)
```

**Sandbox Escape Tests**:
```python
def test_no_network_access():
    """Generated code cannot access network."""
    malicious_code = "import socket; socket.socket().connect(('8.8.8.8', 53))"
    result = safe_execute(malicious_code, timeout=5)
    assert result.success is False
    assert "network" in result.error.lower() or "permission" in result.error.lower()

def test_no_filesystem_escape():
    """Generated code cannot write outside sandbox."""
    malicious_code = "open('/tmp/pwned', 'w').write('pwned')"
    result = safe_execute(malicious_code, timeout=5)
    assert result.success is False
```

### 7.3 Excluded Testing (Baseline)

The following security tests are **not required** for Baseline posture:

- SAST (Static Application Security Testing)
- DAST (Dynamic Application Security Testing)
- Penetration testing
- Red team exercises
- Compliance audits

## 8. Security Controls Summary

### 8.1 Implemented Controls

| Control | Implementation | Status |
|---------|---------------|--------|
| Code execution sandbox | Ollama + subprocess timeout | Required |
| Input validation | CLI argument sanitization | Required |
| Path traversal prevention | Whitelist allowed directories | Required |
| Dependency SBOM | `uv.lock` version locking | Required |
| Vulnerability scanning | `pip-audit` in CI | Required |
| Secret redaction | Log filtering | Required |
| File permissions | Unix permission model | Required |

### 8.2 Deferred Controls

| Control | Trigger for Implementation |
|---------|---------------------------|
| Authentication | Network service exposure |
| Encryption | Sensitive data processing |
| Audit logging | Compliance requirements |
| SAST/DAST | Strong security posture adoption |
| Penetration testing | External deployment |

## 9. Compliance and Standards

### 9.1 Applicable Standards

| Standard | Applicability | Status |
|----------|--------------|--------|
| OWASP Top 10 | Partial (input validation, injection prevention) | Implemented |
| CWE Top 25 | Partial (path traversal, command injection) | Implemented |

### 9.2 Non-Applicable Standards

The following compliance frameworks are **not applicable** for an internal development tool:

- SOC 2 Type I/II
- ISO 27001
- HIPAA
- PCI-DSS
- GDPR (no personal data processed)

## 10. Security Review Schedule

| Review Type | Frequency | Responsible |
|-------------|-----------|-------------|
| Dependency audit | Monthly | Developer |
| Security posture review | Quarterly | Developer |
| Posture upgrade assessment | Annually | Developer |

### 10.1 Posture Upgrade Triggers

Upgrade from Baseline to Strong security posture if:

1. matric-eval is exposed as a network service
2. Multi-user or multi-tenant access is required
3. Sensitive or proprietary data is processed
4. External parties gain access to the system
5. Compliance requirements are introduced

## 11. References

- [Solution Profile](/home/roctinam/dev/matric-eval/.aiwg/intake/solution-profile.md) - Security posture selection rationale
- [Supplementary Requirements](/home/roctinam/dev/matric-eval/.aiwg/requirements/supplementary-requirements.md) - SEC-001 through SEC-005
- [SAD Section 6](/home/roctinam/dev/matric-eval/.aiwg/architecture/SAD.md) - Security Architecture
- [OWASP Top 10](https://owasp.org/Top10/)
- [CWE Top 25](https://cwe.mitre.org/top25/)

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial security posture document |
