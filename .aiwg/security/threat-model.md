# Threat Model

**Document ID**: SEC-TM-001
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Approved
**Methodology**: STRIDE (Simplified for Internal Tool)

## 1. Executive Summary

This threat model analyzes security risks for matric-eval, an internal model evaluation framework. Given the **Baseline security posture** and limited attack surface (local CLI tool, no network exposure), this is a simplified threat model focusing on the primary risk: **code execution of untrusted model outputs**.

**Key Finding**: The primary threat is arbitrary code execution from malicious or unexpected model-generated code. Mitigations rely on subprocess sandboxing, timeouts, and resource limits.

## 2. System Overview

### 2.1 System Description

matric-eval evaluates LLM models by:
1. Sending benchmark prompts to Ollama (local LLM server)
2. Receiving model-generated responses (often code)
3. Executing generated code against test cases
4. Scoring and aggregating results

### 2.2 System Boundaries

```
+------------------------------------------------------------------+
|                    TRUST BOUNDARY: Local Machine                   |
|                                                                    |
|  +----------------+     +----------------+     +----------------+  |
|  |                |     |                |     |                |  |
|  |  matric-eval   |---->|    Ollama      |---->|   LLM Model    |  |
|  |     CLI        |     |  (localhost)   |     | (downloaded)   |  |
|  |                |<----|                |<----|                |  |
|  +----------------+     +----------------+     +----------------+  |
|         |                                                          |
|         v                                                          |
|  +----------------+     +----------------+                         |
|  |   Sandbox      |     |   Results      |                         |
|  | (subprocess)   |     |   (files)      |                         |
|  +----------------+     +----------------+                         |
|                                                                    |
+------------------------------------------------------------------+
                              ^
                              |
                     [No external network access]
```

### 2.3 Data Flow Diagram

```
                      EXTERNAL                    INTERNAL
                    +----------+              +--------------+
                    | Benchmark|              |              |
[1] Dataset Load    | Datasets |------------->| Task Loader  |
                    | (public) |              |              |
                    +----------+              +--------------+
                                                    |
                                                    v
                                              +--------------+
[2] Prompt Submit                             |   Ollama     |
                    +----------+              |    API       |
                    |  Model   |<-------------|  (localhost) |
                    | Response |              |              |
                    +----------+              +--------------+
                         |
                         v
                    +--------------+
[3] Code Execute    |   SANDBOX    |<--------- PRIMARY THREAT SURFACE
                    | (subprocess) |
                    +--------------+
                         |
                         v
                    +--------------+
[4] Results Store   |    File      |
                    |   System     |
                    +--------------+
```

## 3. Asset Inventory

### 3.1 Critical Assets

| Asset | Description | Confidentiality | Integrity | Availability |
|-------|-------------|----------------|-----------|--------------|
| Evaluation Results | Scores, rankings, recommendations | Low | High | Medium |
| Checkpoint State | Resume progress, partial results | Low | High | High |
| Host File System | Local machine files | High | High | High |
| Execution Environment | CPU, memory, network | Medium | High | High |

### 3.2 Supporting Assets

| Asset | Description | Sensitivity |
|-------|-------------|-------------|
| Benchmark Datasets | Public evaluation data (HumanEval, MBPP) | Public |
| Generated Code | Model outputs, test execution | Untrusted |
| Configuration | Ollama endpoint, tier settings | Low |
| Log Files | Execution traces, error details | Internal |

## 4. Threat Actors

### 4.1 Applicable Threat Actors

| Actor | Motivation | Capability | Likelihood |
|-------|------------|------------|------------|
| Malicious Model | Model trained to produce harmful outputs | Medium | Low |
| Compromised Dataset | Tampered benchmark with malicious tests | Low | Very Low |
| Accidental Harm | Model produces unintentionally harmful code | N/A | Medium |

### 4.2 Excluded Threat Actors

The following threat actors are **out of scope** for an internal development tool:

| Actor | Reason for Exclusion |
|-------|---------------------|
| External Attacker | No network exposure |
| Malicious User | Single-user, single-developer environment |
| Insider Threat | Same as developer, no separation needed |
| Supply Chain (Runtime) | Ollama and models are trusted components |

## 5. STRIDE Analysis: Code Execution Component

The code execution sandbox is the **primary threat surface**. This section applies STRIDE analysis to this critical component.

### 5.1 Component Description

```python
def safe_execute(code: str, test: str, timeout: int = 30) -> ExecutionResult:
    """
    Execute model-generated code in a sandboxed subprocess.

    Threats:
    - Code is UNTRUSTED (generated by LLM)
    - May contain malicious or accidental harmful operations
    - Must be isolated from host system
    """
```

### 5.2 STRIDE Threat Matrix

| Threat | Category | Description | Likelihood | Impact | Risk |
|--------|----------|-------------|------------|--------|------|
| T1 | Spoofing | Code impersonates trusted process | Low | Medium | Low |
| T2 | Tampering | Code modifies host files | Medium | High | **High** |
| T3 | Repudiation | Cannot attribute code execution | Low | Low | Low |
| T4 | Information Disclosure | Code reads sensitive files | Medium | High | **High** |
| T5 | Denial of Service | Code exhausts resources | High | Medium | **High** |
| T6 | Elevation of Privilege | Code escapes sandbox | Low | Critical | **Medium** |

### 5.3 Detailed Threat Analysis

#### T1: Spoofing
**Description**: Generated code attempts to impersonate a trusted process or user.

**Attack Scenarios**:
- Code creates files with misleading names (e.g., `system32.dll`)
- Code attempts to modify PATH or environment

**Likelihood**: Low (limited benefit in isolated environment)

**Mitigations**:
- Subprocess runs with same user, no privilege escalation possible
- No network access to impersonate remote services

**Residual Risk**: Low (accepted)

---

#### T2: Tampering
**Description**: Generated code modifies files outside the sandbox directory.

**Attack Scenarios**:
```python
# Malicious code examples
open("/etc/passwd", "a").write("pwned")
os.remove("/home/user/.ssh/id_rsa")
shutil.rmtree("/")
```

**Likelihood**: Medium (models can generate file operations)

**Mitigations**:
| Control | Implementation |
|---------|---------------|
| Directory restriction | Subprocess `cwd` set to isolated temp directory |
| Write filter | Block writes outside sandbox (if using container) |
| File system snapshot | Use tmpfs for execution environment |
| User isolation | Run as unprivileged user (if available) |

**Implementation**:
```python
import tempfile
import subprocess

def safe_execute(code: str, test: str, timeout: int = 30) -> ExecutionResult:
    with tempfile.TemporaryDirectory(prefix="matric_sandbox_") as sandbox:
        # Write code to sandbox
        code_path = os.path.join(sandbox, "solution.py")
        test_path = os.path.join(sandbox, "test.py")

        with open(code_path, "w") as f:
            f.write(code)
        with open(test_path, "w") as f:
            f.write(test)

        # Execute in sandbox with restricted cwd
        result = subprocess.run(
            ["python", test_path],
            cwd=sandbox,
            timeout=timeout,
            capture_output=True,
            # Consider: user= for privilege drop
        )

        return ExecutionResult(
            success=result.returncode == 0,
            stdout=result.stdout.decode(),
            stderr=result.stderr.decode(),
        )
```

**Residual Risk**: Medium (monitor for escaped writes)

---

#### T3: Repudiation
**Description**: Cannot determine which code caused system changes.

**Attack Scenarios**:
- Code creates files, unclear which evaluation produced them
- No audit trail of executed code

**Likelihood**: Low (internal tool, limited concern)

**Mitigations**:
- Generated code saved in `results/run-{id}/{model}/{benchmark}/problems/{id}.json`
- Execution results include stdout, stderr, return code
- Timestamp and context preserved

**Residual Risk**: Low (accepted for internal tool)

---

#### T4: Information Disclosure
**Description**: Generated code reads sensitive information from host system.

**Attack Scenarios**:
```python
# Exfiltrate sensitive files
print(open("/etc/shadow").read())
print(open(os.path.expanduser("~/.ssh/id_rsa")).read())
print(open(os.path.expanduser("~/.aws/credentials")).read())
```

**Likelihood**: Medium (models can generate file read operations)

**Mitigations**:
| Control | Implementation |
|---------|---------------|
| Network isolation | No network access to exfiltrate data |
| Output sanitization | Truncate stdout/stderr in results |
| Container isolation | Full filesystem isolation (optional) |

**Implementation**:
```python
# Network isolation (if available)
subprocess.run(
    ["python", test_path],
    cwd=sandbox,
    timeout=timeout,
    # Linux: use network namespace
    # macOS/Windows: rely on no network code in tests
)
```

**Note**: Without network access, read data cannot be exfiltrated. However, data may appear in stdout/stderr which is saved to results. Consider output truncation for sensitive environments.

**Residual Risk**: Medium (sensitive files readable, but not exfiltrable)

---

#### T5: Denial of Service
**Description**: Generated code exhausts system resources.

**Attack Scenarios**:
```python
# CPU exhaustion
while True: pass

# Memory exhaustion
x = []
while True: x.append("A" * 1000000)

# Disk exhaustion
with open("huge.txt", "w") as f:
    while True: f.write("A" * 1000000)

# Fork bomb
import os
while True: os.fork()
```

**Likelihood**: High (common failure mode for generated code)

**Mitigations**:
| Control | Implementation |
|---------|---------------|
| Timeout | subprocess timeout (30s default) |
| Memory limit | resource.setrlimit() or cgroups |
| Disk limit | tmpfs with size limit |
| Process limit | ulimit -u or cgroups |

**Implementation**:
```python
import resource
import subprocess

def safe_execute(code: str, test: str, timeout: int = 30) -> ExecutionResult:
    # Create wrapper script with resource limits
    wrapper = f"""
import resource
import sys

# Memory limit: 1GB
resource.setrlimit(resource.RLIMIT_AS, (1024*1024*1024, 1024*1024*1024))

# CPU time limit: {timeout} seconds
resource.setrlimit(resource.RLIMIT_CPU, ({timeout}, {timeout}))

# File size limit: 100MB
resource.setrlimit(resource.RLIMIT_FSIZE, (100*1024*1024, 100*1024*1024))

# Number of processes: 10
resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))

exec(open(sys.argv[1]).read())
"""

    with tempfile.TemporaryDirectory(prefix="matric_sandbox_") as sandbox:
        # ... setup code and test files ...

        result = subprocess.run(
            ["python", "-c", wrapper, test_path],
            cwd=sandbox,
            timeout=timeout + 5,  # Allow cleanup time
            capture_output=True,
        )
```

**Residual Risk**: Low (with proper limits)

---

#### T6: Elevation of Privilege
**Description**: Generated code escapes sandbox to gain elevated privileges.

**Attack Scenarios**:
- Exploit Python interpreter vulnerability
- Use ptrace to attach to parent process
- Exploit kernel vulnerability via syscall

**Likelihood**: Low (requires 0-day or significant vulnerability)

**Mitigations**:
| Control | Implementation |
|---------|---------------|
| No setuid | Subprocess inherits user, no elevation possible |
| seccomp (optional) | Restrict allowed syscalls |
| Container (optional) | Docker/Podman for full isolation |

**Container Option** (for full tier):
```python
def container_execute(code: str, test: str, timeout: int = 30) -> ExecutionResult:
    """Execute in Docker container for maximum isolation."""
    with tempfile.TemporaryDirectory() as sandbox:
        # Write files to sandbox
        # ...

        result = subprocess.run([
            "docker", "run",
            "--rm",
            "--network=none",
            "--memory=1g",
            "--cpus=1",
            "--pids-limit=50",
            "--read-only",
            "-v", f"{sandbox}:/workspace:rw",
            "-w", "/workspace",
            "python:3.11-slim",
            "python", "test.py"
        ], timeout=timeout + 10, capture_output=True)
```

**Residual Risk**: Low (kernel exploit unlikely, container provides defense-in-depth)

## 6. Key Threats and Mitigations Summary

### 6.1 High-Priority Threats

| ID | Threat | Risk Level | Primary Mitigation | Status |
|----|--------|------------|-------------------|--------|
| T2 | File System Tampering | High | Sandbox directory isolation | Required |
| T4 | Information Disclosure | High | No network + output limits | Required |
| T5 | Resource Exhaustion | High | Timeouts + resource limits | Required |

### 6.2 Mitigation Implementation Matrix

| Mitigation | T1 | T2 | T3 | T4 | T5 | T6 | Priority |
|------------|----|----|----|----|----|----|----------|
| Sandbox directory | - | X | - | - | - | - | P1 |
| Subprocess timeout | - | - | - | - | X | - | P1 |
| Memory limits | - | - | - | - | X | - | P1 |
| Network isolation | - | - | - | X | - | - | P1 |
| Result logging | - | - | X | - | - | - | P2 |
| Container execution | - | X | - | X | X | X | P3 (optional) |

## 7. Additional Threat Considerations

### 7.1 Dataset Integrity

**Threat**: Compromised benchmark dataset with malicious test cases.

**Scenario**: Attacker modifies HumanEval or MBPP dataset to include tests that exploit the execution environment.

**Mitigations**:
- Download datasets from official sources only (HuggingFace, GitHub releases)
- Validate dataset checksums before use
- Store datasets as read-only after download

**Residual Risk**: Very Low (public datasets are well-monitored)

### 7.2 Dependency Confusion

**Threat**: Malicious package installed via typosquatting or dependency confusion.

**Scenario**: `pip install inspect-ai` installs a malicious package instead of legitimate `inspect_ai`.

**Mitigations**:
- Use `uv.lock` for reproducible installs
- Run `pip-audit` to detect known vulnerabilities
- Review `pyproject.toml` dependencies manually

**Residual Risk**: Low (locked dependencies reduce attack surface)

### 7.3 Ollama Model Compromise

**Threat**: Downloaded Ollama model contains malicious weights or code.

**Scenario**: Model on Ollama Hub has been compromised to produce harmful outputs.

**Mitigations**:
- Download models from official Ollama library
- Validate model checksums (SHA256)
- Trust but verify: sandbox execution handles malicious outputs

**Residual Risk**: Low (Ollama library is curated, sandbox provides defense-in-depth)

## 8. Security Controls Summary

### 8.1 Required Controls

| Control | Component | Implementation | Verification |
|---------|-----------|---------------|--------------|
| Subprocess timeout | Code execution | `subprocess.run(timeout=30)` | Unit test |
| Memory limit | Code execution | `resource.setrlimit(RLIMIT_AS)` | Unit test |
| CPU limit | Code execution | `resource.setrlimit(RLIMIT_CPU)` | Unit test |
| Sandbox directory | Code execution | `tempfile.TemporaryDirectory()` | Unit test |
| Input validation | CLI | Model name regex, path validation | Unit test |
| Dataset checksums | Data loading | SHA256 verification | Integration test |

### 8.2 Optional Controls (Defense-in-Depth)

| Control | Benefit | Implementation Effort |
|---------|---------|----------------------|
| Docker container | Full isolation | Medium |
| seccomp profile | Syscall filtering | High |
| Network namespace | Network isolation (Linux) | Medium |
| Read-only filesystem | Prevent all writes | Low (with container) |

### 8.3 Control Effectiveness

```
                            THREAT COVERAGE
Control                  T1   T2   T3   T4   T5   T6
---------------------------------------------------------
Subprocess timeout       -    -    -    -    +++  -
Memory limits           -    -    -    -    +++  -
Sandbox directory       -    ++   -    -    +    -
Network isolation       -    -    -    +++  -    -
Container (optional)    +    +++  +    +++  ++   ++

Legend: +++ Strong, ++ Moderate, + Weak, - No effect
```

## 9. Residual Risk Assessment

### 9.1 Accepted Risks

| Risk | Severity | Acceptance Rationale |
|------|----------|---------------------|
| Sensitive file read | Medium | No network exfiltration possible |
| Resource spike before timeout | Low | Brief impact, auto-recovery |
| Sandbox escape via 0-day | Low | Extremely unlikely, container available |

### 9.2 Risk Mitigation Roadmap

| Phase | Milestone | Risk Reduction |
|-------|-----------|----------------|
| v1.0 | Subprocess sandbox + timeouts | 60% |
| v1.1 | Resource limits (memory, CPU, processes) | 80% |
| v2.0 | Docker container option for full tier | 95% |

## 10. Security Testing Requirements

### 10.1 Sandbox Escape Tests

```python
# tests/test_sandbox.py

class TestSandboxSecurity:
    """Security tests for code execution sandbox."""

    def test_cannot_read_etc_passwd(self):
        """Sandbox cannot read system files."""
        code = "print(open('/etc/passwd').read())"
        result = safe_execute(code, "")
        # Either permission denied or file not visible
        assert "passwd" not in result.stdout

    def test_cannot_write_outside_sandbox(self):
        """Sandbox cannot write to arbitrary paths."""
        code = "open('/tmp/escaped', 'w').write('pwned')"
        result = safe_execute(code, "")
        assert not os.path.exists("/tmp/escaped")

    def test_timeout_prevents_infinite_loop(self):
        """Infinite loop terminates within timeout."""
        code = "while True: pass"
        start = time.time()
        result = safe_execute(code, "", timeout=5)
        elapsed = time.time() - start
        assert elapsed < 10  # Timeout + buffer
        assert not result.success

    def test_memory_limit_prevents_exhaustion(self):
        """Memory exhaustion terminates cleanly."""
        code = "x = []; exec('while True: x.append(\"A\"*1000000)')"
        result = safe_execute(code, "", timeout=30)
        assert not result.success
        # System should remain responsive

    def test_fork_bomb_contained(self):
        """Fork bomb is contained by process limits."""
        code = "import os\nwhile True: os.fork()"
        result = safe_execute(code, "", timeout=10)
        assert not result.success
```

### 10.2 Input Fuzzing Tests

```python
# tests/test_input_validation.py

MALICIOUS_MODEL_NAMES = [
    "../../../etc/passwd",
    "model; rm -rf /",
    "model$(cat /etc/passwd)",
    "model`whoami`",
    "model\nmalicious",
    "a" * 10000,  # Length attack
    "\x00null\x00byte",
]

MALICIOUS_PATHS = [
    "/etc/passwd",
    "../../../etc/passwd",
    "results/../../../tmp",
    "/dev/null",
    "\\\\server\\share",  # UNC path
]

@pytest.mark.parametrize("name", MALICIOUS_MODEL_NAMES)
def test_model_name_sanitization(name):
    """Malicious model names are rejected."""
    with pytest.raises(ValidationError):
        validate_model_name(name)

@pytest.mark.parametrize("path", MALICIOUS_PATHS)
def test_path_sanitization(path):
    """Malicious paths are rejected."""
    with pytest.raises(ValidationError):
        validate_output_path(path)
```

## 11. Review and Maintenance

### 11.1 Review Schedule

| Review Type | Frequency | Trigger |
|-------------|-----------|---------|
| Threat model review | Annually | - |
| Control verification | Quarterly | - |
| Ad-hoc review | As needed | New feature, security incident |

### 11.2 Update Triggers

This threat model should be updated when:

1. Network exposure is added (API server mode)
2. Multi-user access is implemented
3. Sensitive data processing is introduced
4. New code execution paths are added
5. Container/sandbox implementation changes
6. Security incident occurs

## 12. References

- [Security Posture](/home/roctinam/dev/matric-eval/.aiwg/security/security-posture.md) - Overall security stance
- [Supplementary Requirements](/home/roctinam/dev/matric-eval/.aiwg/requirements/supplementary-requirements.md) - SEC-001 through SEC-005
- [SAD Section 6](/home/roctinam/dev/matric-eval/.aiwg/architecture/SAD.md) - Security Architecture
- [STRIDE Threat Modeling](https://docs.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats)
- [Python subprocess security](https://docs.python.org/3/library/subprocess.html#security-considerations)

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial threat model |
