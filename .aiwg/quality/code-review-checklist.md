# Code Review Checklist - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Purpose**: Comprehensive code review template for all changes
**Profile**: Production (80%+ test coverage required)
**Last Updated**: 2026-01-24

---

## Overview

This checklist ensures consistent, thorough code reviews for all changes to matric-eval. For solo developers, this serves as a self-review checklist. For teams, both author and reviewer should verify these items.

**Review Philosophy**:
- Quality is non-negotiable for critical components
- Catching defects in review is 10x cheaper than in production
- Reviews improve code quality AND developer knowledge
- Constructive feedback strengthens the codebase

**Mandatory Items**: Items marked with ⚠️ are BLOCKING - code cannot merge if these fail.

**Review Time Expectations**:
- Small changes (<100 LOC): 15-30 minutes
- Medium changes (100-500 LOC): 30-60 minutes
- Large changes (>500 LOC): 60-120 minutes (or request split into smaller PRs)

---

## Pre-Review Checklist (Author)

Before requesting review or self-reviewing, the author must complete:

- [ ] All tests passing locally (`pytest`)
- [ ] Code coverage maintained or increased
- [ ] Linter passing with no warnings (`ruff check`)
- [ ] Type checker passing in strict mode (`mypy --strict`)
- [ ] Security scanner passing (`bandit -r src/`)
- [ ] Pre-commit hooks passing (if configured)
- [ ] Self-review of diff completed (line-by-line in GitHub)
- [ ] PR description explains what, why, and how
- [ ] Related issues linked in PR description

**Self-Review Protocol**:
1. View your own PR in GitHub (not local diff)
2. Review each changed file as if you're a peer reviewer
3. Add inline comments on areas needing reviewer attention
4. Document design decisions in PR description
5. For critical changes: Sleep on it, review again the next day

---

## 1. Functionality Correctness

### 1.1 Requirements Alignment ⚠️

- [ ] Change implements stated requirement or fixes described bug
- [ ] All acceptance criteria met (if specified in issue)
- [ ] Edge cases identified and handled
- [ ] Error conditions identified and handled
- [ ] No scope creep (unrelated changes separated into different PRs)

**Questions to Ask**:
- Does this solve the problem completely?
- Are there unhandled edge cases?
- What happens if inputs are malformed, null, or extreme values?
- What happens if external services (Ollama) fail?

### 1.2 Logic Correctness ⚠️

- [ ] Algorithms are correct and efficient
- [ ] Conditional logic is sound (no off-by-one errors)
- [ ] Loop termination conditions are correct
- [ ] Recursion has proper base cases (if applicable)
- [ ] Math operations are correct (especially floating point)
- [ ] Comparison operators are correct (==, !=, <, >, etc.)

**Critical Components (Extra Scrutiny)**:
- Scorers: Scoring logic must be 100% correct
- State management: Checkpoint/resume logic must prevent data loss
- Code extraction: Parsing LLM output must handle malformed responses
- Validation: Pass/fail decisions must be accurate

**Red Flags**:
- Complex boolean expressions without extraction to named variables
- Copy-pasted code blocks (DRY violation)
- Magic numbers without named constants
- Commented-out code (remove or explain why keeping)

### 1.3 API Contracts

- [ ] Function signatures match documented interfaces
- [ ] Return types are correct and consistent
- [ ] Exceptions documented and appropriate
- [ ] Breaking changes are documented and justified
- [ ] Backward compatibility maintained (or migration path provided)

**For Public APIs**:
- [ ] Docstring complete with parameters, return type, exceptions
- [ ] Examples provided in docstring or documentation
- [ ] Type hints comprehensive and accurate

---

## 2. Test Coverage Requirements

### 2.1 Unit Tests ⚠️

- [ ] New code has unit tests (minimum 80% coverage)
- [ ] Critical components have 100% coverage (scorers, state management)
- [ ] Tests are isolated (no dependencies on external services)
- [ ] Tests use mocks/fixtures appropriately
- [ ] Tests are fast (<1 second per test)
- [ ] Test names clearly describe scenario (test_should_X_when_Y)

**Test Quality Checks**:
- [ ] Tests verify behavior, not implementation
- [ ] Assertions are specific (not just "assert result")
- [ ] Edge cases tested (empty input, null, extreme values)
- [ ] Error cases tested (exceptions raised as expected)
- [ ] Parameterized tests used for similar scenarios

**Critical Component Test Requirements**:

For **scorers** (`src/matric_eval/scorers/`):
- [ ] Test with correct output (should pass)
- [ ] Test with incorrect output (should fail)
- [ ] Test with malformed output (should handle gracefully)
- [ ] Test with edge cases (empty string, very long output, special chars)
- [ ] Test reproducibility (same input → same score)

For **state management** (`src/matric_eval/state/`):
- [ ] Test checkpoint write succeeds
- [ ] Test checkpoint write is atomic (no partial writes)
- [ ] Test resume from checkpoint restores correct state
- [ ] Test gap detection identifies missing results
- [ ] Test concurrent access prevention (lock files)
- [ ] Test corrupted checkpoint handling

### 2.2 Integration Tests

- [ ] Integration tests added for new component interactions
- [ ] Tests use real Ollama instance (or controlled mock)
- [ ] Tests clean up resources (no leaked temp files, processes)
- [ ] Tests are deterministic (not flaky)
- [ ] Tests have reasonable timeout (<5 seconds per test)

**Integration Scenarios to Test**:
- Ollama API calls (model loading, inference, errors)
- File system operations (checkpoint writes, resume reads)
- CLI to core library integration
- Benchmark execution end-to-end

### 2.3 Regression Tests ⚠️

- [ ] Bug fix includes regression test that would have caught the bug
- [ ] Test fails before fix, passes after fix
- [ ] Test added to permanent suite (not skipped)

**Regression Test Naming**:
```python
def test_regression_issue_123_checkpoint_corruption():
    """Regression test for GitHub issue #123: Checkpoint corrupts on SIGTERM."""
    # Test that reproduces the bug
    # Should fail before fix, pass after fix
```

### 2.4 Coverage Metrics ⚠️

- [ ] Overall coverage maintained or increased (target: 80%+)
- [ ] Critical component coverage 100% (scorers, state management)
- [ ] No significant coverage decrease in any module

**Coverage Exemptions** (must justify):
- [ ] `if __name__ == "__main__"` blocks (CLI entry points)
- [ ] Exception handling for truly unreachable code (document why)
- [ ] Deprecated code scheduled for removal

---

## 3. Security Considerations

### 3.1 Input Validation ⚠️

- [ ] All user input validated before use
- [ ] File paths validated (no path traversal: `../../../etc/passwd`)
- [ ] Command-line arguments validated
- [ ] Environment variables validated
- [ ] External API responses validated (Ollama responses)

**Validation Checklist**:
- [ ] Type validation (is input expected type?)
- [ ] Range validation (is number within bounds?)
- [ ] Length validation (is string reasonable length?)
- [ ] Format validation (does string match expected pattern?)
- [ ] Whitelist validation (is value in allowed set?)

### 3.2 Code Execution Safety ⚠️

- [ ] LLM-generated code executed in sandbox (Docker)
- [ ] Resource limits enforced (timeout, memory, CPU)
- [ ] Network access restricted (no external calls from sandbox)
- [ ] File system access restricted (temp directory only)
- [ ] Dangerous operations prevented (exec, eval, subprocess in LLM code)

**Sandbox Requirements**:
- [ ] Docker container with limited permissions
- [ ] Timeout enforcement (default: 30 seconds per problem)
- [ ] Memory limit (default: 512MB per execution)
- [ ] CPU limit (default: 1 core)
- [ ] No internet access from sandbox

### 3.3 Data Exposure

- [ ] No secrets in code (API keys, passwords, tokens)
- [ ] No secrets in logs (sensitive data redacted)
- [ ] No PII in test data or examples
- [ ] Temporary files cleaned up after use
- [ ] Checkpoint files have appropriate permissions (not world-readable)

**Secret Management**:
- [ ] Use environment variables for secrets
- [ ] Never log environment variables
- [ ] Never commit `.env` files
- [ ] Document required environment variables

### 3.4 Dependency Security ⚠️

- [ ] New dependencies justified (not added unnecessarily)
- [ ] New dependencies scanned for vulnerabilities (`pip-audit`)
- [ ] Dependencies pinned to specific versions
- [ ] Dependencies from trusted sources (PyPI)

**Dependency Review**:
- [ ] License compatible with project (check LICENSE file)
- [ ] Actively maintained (commits within 6 months)
- [ ] No known critical/high vulnerabilities
- [ ] Minimal transitive dependencies (fewer is better)

### 3.5 Error Handling and Information Disclosure

- [ ] Error messages don't leak sensitive information
- [ ] Stack traces sanitized in production logs
- [ ] User-facing errors are actionable (suggest fix)
- [ ] Internal errors logged with context (for debugging)

**Error Message Guidelines**:
- Good: "Checkpoint file not found. Run evaluation first."
- Bad: "FileNotFoundError at /home/user/.secret/checkpoint.json"

---

## 4. Performance Implications

### 4.1 Algorithm Complexity

- [ ] Algorithm complexity analyzed (Big O notation)
- [ ] No nested loops with O(n²) or worse (unless necessary and justified)
- [ ] No redundant computations (cache results when appropriate)
- [ ] No unnecessary data copying (use references/views when safe)

**Performance Red Flags**:
- Nested loops over large datasets
- Repeated database/API queries in loops (N+1 problem)
- Loading entire files into memory (stream when possible)
- Synchronous I/O in loops (use async or batch)
- Unnecessary string concatenation in loops (use join)

### 4.2 Resource Usage

- [ ] Memory usage reasonable (no unnecessary large allocations)
- [ ] File handles closed properly (use context managers)
- [ ] Processes cleaned up (no zombie processes)
- [ ] Threads/async tasks have proper cleanup
- [ ] No circular references preventing garbage collection

**Resource Management Patterns**:
```python
# Good: Context manager ensures cleanup
with open(checkpoint_file, 'w') as f:
    json.dump(state, f)

# Bad: File handle might leak on exception
f = open(checkpoint_file, 'w')
json.dump(state, f)
f.close()
```

### 4.3 Database and API Efficiency

- [ ] No N+1 query patterns (batch queries when possible)
- [ ] Appropriate indexing considered (for future database use)
- [ ] API calls minimized (cache results when appropriate)
- [ ] Pagination used for large result sets
- [ ] Retries with exponential backoff for transient failures

**Ollama API Efficiency**:
- [ ] Model loaded once, reused for multiple inferences
- [ ] Inference requests batched when possible
- [ ] Timeouts configured appropriately
- [ ] Connection pooling used (if multiple concurrent requests)

### 4.4 Caching and Memoization

- [ ] Expensive computations cached (when safe)
- [ ] Cache invalidation strategy defined
- [ ] Cache size bounded (no unbounded growth)
- [ ] Thread-safe caching (if multi-threaded)

**Caching Opportunities**:
- Dataset loading (load once, reuse)
- Model metadata (avoid repeated Ollama queries)
- Parsed test data (don't re-parse on every run)

### 4.5 Performance Testing

- [ ] Performance baseline established (if applicable)
- [ ] Performance regression tests added (if critical path)
- [ ] Profiling results reviewed (if optimization attempted)
- [ ] Optimization validated with benchmarks

**Performance Thresholds** (must not regress):
- Smoke tier: <2 minutes total
- Quick tier: <20 minutes total
- State checkpoint write: <100ms
- Resume overhead: <5 seconds

---

## 5. Documentation Completeness

### 5.1 Code Documentation ⚠️

- [ ] All public functions/classes have docstrings
- [ ] Docstrings include parameters, return type, exceptions
- [ ] Complex logic has inline comments explaining "why"
- [ ] Type hints comprehensive and accurate
- [ ] TODOs tracked with issue numbers (TODO: #123 implement caching)

**Docstring Template** (NumPy style):
```python
def evaluate_benchmark(
    model: str,
    benchmark: str,
    tier: str = "smoke"
) -> EvaluationResult:
    """
    Evaluate a model on a specific benchmark.

    Parameters
    ----------
    model : str
        Ollama model name (e.g., "llama3.2:3b")
    benchmark : str
        Benchmark name (e.g., "humaneval")
    tier : str, optional
        Evaluation tier: "smoke", "quick", or "full" (default: "smoke")

    Returns
    -------
    EvaluationResult
        Object containing scores, metadata, and timing information

    Raises
    ------
    ModelNotFoundError
        If the specified model is not available in Ollama
    BenchmarkNotFoundError
        If the specified benchmark is not recognized

    Examples
    --------
    >>> result = evaluate_benchmark("llama3.2:3b", "humaneval", tier="smoke")
    >>> print(result.score)
    0.85
    """
```

### 5.2 User Documentation

- [ ] New features documented in user docs (README or docs/)
- [ ] CLI help text updated (`--help` output)
- [ ] Examples provided for new functionality
- [ ] Migration guide provided (if breaking change)

**User Documentation Checklist**:
- [ ] Installation instructions (if dependencies changed)
- [ ] Usage examples (with expected output)
- [ ] Configuration options (environment variables, CLI flags)
- [ ] Troubleshooting common issues

### 5.3 Developer Documentation

- [ ] Architecture changes documented (ADR if significant)
- [ ] Design decisions explained (in PR or comments)
- [ ] Testing approach documented
- [ ] Known limitations documented

**When to Write an ADR**:
- New framework or library added
- Significant architectural change
- Trade-off decision with multiple valid options
- Deviation from established patterns

### 5.4 Changelog and Release Notes

- [ ] CHANGELOG.md updated (if applicable)
- [ ] Breaking changes highlighted
- [ ] Deprecations noted
- [ ] Migration path described

---

## 6. Code Style and Conventions

### 6.1 Python Style (PEP 8) ⚠️

- [ ] Linter passing with no warnings (`ruff check`)
- [ ] Consistent naming conventions (snake_case for functions/vars)
- [ ] Line length within limit (default: 88 for Black, 120 for matric-eval)
- [ ] Imports organized (standard lib, third-party, local)
- [ ] No wildcard imports (`from module import *`)

**Naming Conventions**:
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Protected: `__double_leading_underscore` (rare)

### 6.2 Type Hints ⚠️

- [ ] All public functions have type hints
- [ ] Type hints accurate and complete
- [ ] mypy strict mode passing (`mypy --strict`)
- [ ] Complex types use typing module (List, Dict, Optional, Union)
- [ ] Return types explicit (not just inferred)

**Type Hint Examples**:
```python
from typing import Optional, List, Dict, Any

def load_checkpoint(run_id: str) -> Optional[Dict[str, Any]]:
    """Load checkpoint state for a run."""
    # Returns None if checkpoint doesn't exist
    ...

def get_benchmark_scores(results: List[Result]) -> Dict[str, float]:
    """Calculate average scores per benchmark."""
    ...
```

### 6.3 Code Organization

- [ ] Functions are focused (single responsibility)
- [ ] Functions are short (<50 lines, ideally <20)
- [ ] Classes are cohesive (related functionality grouped)
- [ ] Modules are focused (one purpose per module)
- [ ] No circular dependencies between modules

**Code Smell Detection**:
- Function >50 lines → Consider splitting
- Function with >4 parameters → Consider object or config
- Nesting >4 levels deep → Refactor (extract functions)
- Duplicate code blocks → Extract to shared function
- Complex boolean → Extract to named variable/function

### 6.4 Error Handling

- [ ] Exceptions used appropriately (not for control flow)
- [ ] Custom exceptions defined for domain errors
- [ ] Exceptions caught at appropriate level
- [ ] Error messages are clear and actionable
- [ ] Resources cleaned up in finally blocks (or use context managers)

**Exception Hierarchy**:
```python
class MatricEvalError(Exception):
    """Base exception for matric-eval."""

class ModelNotFoundError(MatricEvalError):
    """Raised when Ollama model not found."""

class CheckpointCorruptedError(MatricEvalError):
    """Raised when checkpoint file is corrupted."""
```

### 6.5 Comments and Clarity

- [ ] Comments explain "why", not "what"
- [ ] Complex logic has explanatory comments
- [ ] No commented-out code (delete or use feature flags)
- [ ] TODOs have issue numbers and owners
- [ ] Code is self-documenting (clear names, simple logic)

**Good Comment**:
```python
# MBPP requires function name in prompt, but it's not provided in dataset.
# Extract from test assertion: assert func(...) == expected
function_name = extract_function_name(test_assertion)
```

**Bad Comment**:
```python
# Extract function name
function_name = extract_function_name(test_assertion)  # What we're doing
```

---

## 7. Testing and CI/CD

### 7.1 Test Execution ⚠️

- [ ] All tests passing locally before PR
- [ ] Tests passing in CI (GitHub Actions)
- [ ] No flaky tests (tests pass consistently)
- [ ] Tests run in reasonable time (<15 min total in CI)

**Flaky Test Protocol**:
- If test is flaky, it MUST be fixed or disabled (with issue filed)
- Never merge with known flaky tests
- Investigate root cause (race condition, external dependency, timing)

### 7.2 CI Pipeline

- [ ] CI configuration updated (if new dependencies or scripts)
- [ ] CI passes on target branch (main/develop)
- [ ] No new warnings in CI output
- [ ] Coverage report generated and reviewed

**CI Checks** (all must pass):
- [ ] Linter (ruff)
- [ ] Type checker (mypy)
- [ ] Security scanner (bandit)
- [ ] Unit tests
- [ ] Integration tests
- [ ] Coverage report (80%+ maintained)

### 7.3 Deployment Readiness

- [ ] No breaking changes (or documented migration path)
- [ ] Backward compatibility maintained
- [ ] Database migrations provided (if applicable)
- [ ] Configuration changes documented
- [ ] Rollback plan documented (if high-risk change)

---

## 8. Git and Version Control

### 8.1 Commit Quality

- [ ] Commits are atomic (one logical change per commit)
- [ ] Commit messages follow conventions (conventional commits)
- [ ] Commit messages explain "why" in body
- [ ] No merge commits (rebase or squash before merge)
- [ ] Sensitive data not committed (check with git log --stat)

**Commit Message Format**:
```
type(scope): subject line (50 chars max)

Optional body explaining why this change was made.
Can be multiple paragraphs.

Fixes #123
```

**Types**: feat, fix, docs, style, refactor, test, chore

### 8.2 Branch Management

- [ ] Branch naming follows convention (feature/, bugfix/, hotfix/)
- [ ] Branch up-to-date with main/develop
- [ ] No merge conflicts
- [ ] Branch will be deleted after merge

### 8.3 Pull Request Quality

- [ ] PR title is descriptive
- [ ] PR description explains what, why, and how
- [ ] Related issues linked
- [ ] Screenshots included (if UI change)
- [ ] Breaking changes highlighted
- [ ] Reviewers assigned (or self-review documented)

**PR Description Template**:
```markdown
## What
Brief description of changes

## Why
Rationale for changes (link to issue)

## How
Implementation approach

## Testing
How was this tested?

## Checklist
- [ ] Tests added
- [ ] Documentation updated
- [ ] Breaking changes documented

Fixes #123
```

---

## 9. Critical Component Reviews (Extra Scrutiny)

### 9.1 Scorers (`src/matric_eval/scorers/`)

**Mandatory Checks** (100% required):
- [ ] Scoring logic is mathematically correct
- [ ] All edge cases handled (empty output, malformed output)
- [ ] Deterministic (same input always produces same score)
- [ ] Well-tested (100% coverage required)
- [ ] Validated against reference implementation (if public benchmark)

**Scorer-Specific Questions**:
- What happens if LLM output is empty?
- What happens if LLM output is malformed (invalid JSON, wrong format)?
- What happens if LLM output is correct but differently formatted?
- Does this scorer match the reference implementation?

**Validation Approach**:
- Run scorer on known-good examples (should pass)
- Run scorer on known-bad examples (should fail)
- Run scorer on edge cases (should handle gracefully)
- Compare results to reference implementation (if available)

### 9.2 State Management (`src/matric_eval/state/`)

**Mandatory Checks** (100% required):
- [ ] Checkpoint writes are atomic (no partial writes)
- [ ] Resume logic correctly restores state
- [ ] Gap detection accurately identifies missing results
- [ ] No data loss in any scenario (fault injection tested)
- [ ] Lock files prevent concurrent access
- [ ] Corrupted checkpoint files detected and reported

**State Management Questions**:
- What happens if process killed during checkpoint write?
- What happens if checkpoint file corrupted?
- What happens if two processes try to resume same run?
- What happens if disk full during checkpoint write?

**Fault Injection Testing**:
- Kill process during checkpoint write (should detect corruption)
- Corrupt checkpoint file manually (should report error)
- Fill disk during checkpoint write (should fail gracefully)
- Concurrent resume attempts (should prevent with lock file)

### 9.3 Code Extraction (`src/matric_eval/extractors/`)

**Mandatory Checks**:
- [ ] Handles markdown code fences (```python, ```py, ```)
- [ ] Handles inline code (without fences)
- [ ] Handles multiple code blocks (takes first/last/all as appropriate)
- [ ] Handles language tags (python, py, Python, PYTHON)
- [ ] Preserves indentation
- [ ] Removes non-code artifacts (explanation text)

**Extraction Edge Cases**:
- No code fences (raw code)
- Multiple code fences (which to use?)
- Nested code fences (markdown within markdown)
- Code with backticks inside (escape handling)
- Empty code block (what to return?)

### 9.4 CLI (`src/matric_eval/cli.py`)

**Mandatory Checks**:
- [ ] All flags documented in --help
- [ ] Flag combinations validated (e.g., --resume requires --run-id)
- [ ] Error messages actionable
- [ ] Progress output useful (not too verbose or too quiet)
- [ ] Exit codes correct (0 success, non-zero failure)

**CLI Testing**:
- Run with --help (should show usage)
- Run with invalid flags (should show error)
- Run with missing required args (should show error)
- Run with conflicting args (should show error)

---

## 10. Review Sign-Off

### 10.1 Reviewer Checklist (Final)

- [ ] All mandatory items (⚠️) verified
- [ ] Code quality meets standards
- [ ] Tests are comprehensive and passing
- [ ] Documentation is complete
- [ ] No security concerns
- [ ] Performance implications acceptable
- [ ] Feedback provided (if any)

### 10.2 Review Outcomes

**Approve** ✅:
- All mandatory items verified
- No blocking issues
- Minor comments can be addressed in follow-up

**Approve with Comments** ✅📝:
- All mandatory items verified
- Non-blocking suggestions provided
- Author can merge and address in follow-up

**Request Changes** ⚠️:
- One or more mandatory items failed
- Blocking issues must be addressed
- Re-review required after changes

**Block** ❌:
- Critical security or correctness issue
- Architectural concern requiring discussion
- Scope too large (split into smaller PRs)

### 10.3 Self-Review Sign-Off (Solo Developer)

For solo developers, document self-review completion:

```markdown
## Self-Review Checklist

Completed by: [Your Name]
Date: YYYY-MM-DD
Review Duration: X minutes

- [x] Pre-review checklist completed
- [x] Functionality correctness verified
- [x] Tests comprehensive (80%+ coverage)
- [x] Security considerations addressed
- [x] Performance implications assessed
- [x] Documentation complete
- [x] Code style compliant
- [x] Critical components extra scrutiny (if applicable)

**Notes**:
- [Any areas of concern or follow-up needed]

**Approval**: ✅ Ready to merge
```

---

## 11. Common Review Patterns

### 11.1 First-Time Contributor (Solo Developer New to Codebase)

Focus on:
- [ ] Code style alignment with existing patterns
- [ ] Test coverage meets project standards
- [ ] Documentation follows project conventions
- [ ] Understanding of architecture (guide if needed)

### 11.2 Bug Fix

Focus on:
- [ ] Root cause addressed (not just symptom)
- [ ] Regression test added
- [ ] Similar bugs elsewhere (search codebase)
- [ ] Related code reviewed (potential related bugs)

### 11.3 Refactoring

Focus on:
- [ ] Behavior preserved (no functional changes)
- [ ] Tests unchanged or improved (not weakened)
- [ ] Complexity reduced (justified improvement)
- [ ] No scope creep (refactor + feature in separate PRs)

### 11.4 Performance Optimization

Focus on:
- [ ] Baseline established (before optimization)
- [ ] Improvement measured (with benchmarks)
- [ ] Optimization justified (not premature)
- [ ] No correctness regression

### 11.5 Security Fix

Focus on:
- [ ] Vulnerability completely addressed
- [ ] No bypass possible
- [ ] Similar issues elsewhere (audit codebase)
- [ ] Security scan passing
- [ ] Disclosure handled appropriately

---

## Appendix A: Review Time Guidelines

| Change Size | Lines of Code | Review Time | Approach |
|-------------|---------------|-------------|----------|
| Trivial | 1-10 LOC | 5-10 min | Quick scan, focus on correctness |
| Small | 10-100 LOC | 15-30 min | Thorough review, all checklist items |
| Medium | 100-500 LOC | 30-60 min | Deep review, consider architecture |
| Large | 500-1000 LOC | 60-120 min | Very thorough, request split if possible |
| X-Large | >1000 LOC | Request split | Too large for effective review |

**Recommendation**: Keep PRs <500 LOC when possible. Larger changes are harder to review thoroughly.

---

## Appendix B: Review Anti-Patterns

| Anti-Pattern | Why It's Bad | Response |
|--------------|--------------|----------|
| Rubber-stamp approval | Misses defects, no learning | Review thoroughly or decline |
| Nitpick only | Misses big issues | Focus on critical items first |
| Request perfection | Delays progress unnecessarily | Focus on "good enough" with follow-up |
| Review own code immediately | Miss obvious issues | Sleep on it, review fresh |
| Skip tests | Misses coverage gaps | Always review tests |
| Ignore performance | Performance bugs are bugs | Consider performance implications |

---

## Appendix C: Reviewer Feedback Guidelines

### Giving Feedback

**Principles**:
- Be kind and respectful
- Be specific (cite line numbers)
- Explain "why" (educate, don't dictate)
- Suggest alternatives (don't just criticize)
- Acknowledge good work (praise where deserved)

**Feedback Levels**:
- **Blocking**: "This must be changed before merge"
- **Strong suggestion**: "Consider this approach instead"
- **Nitpick**: "Not blocking, but FYI"
- **Question**: "Can you explain why you chose this?"
- **Praise**: "Great approach here!"

**Example Feedback**:
```markdown
**Blocking**: This creates a SQL injection vulnerability.
Use parameterized queries instead:
`cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`
```

### Receiving Feedback

**Principles**:
- Assume good intent (reviewer wants to help)
- Ask clarifying questions
- Defend decisions respectfully (if justified)
- Acknowledge mistakes gracefully
- Learn from feedback

**Responses**:
- "Good catch, fixing now"
- "Can you clarify what you mean by X?"
- "I chose this approach because Y, but I'm open to alternatives"
- "Thanks, I learned something new!"

---

## Document Control

**Version**: 1.0
**Created**: 2026-01-24
**Last Updated**: 2026-01-24
**Next Review**: End of Construction Phase (Week 6)
**Approval Authority**: Solo Python Developer (roctinam)

**Change History**:
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial code review checklist |

---

**END OF CODE REVIEW CHECKLIST**
