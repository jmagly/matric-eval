# ADR-001: Python Core with Language Bindings

**Status**: Accepted
**Date**: 2026-01-24
**Decision Makers**: matric-eval development team
**Supersedes**: N/A

## Context

The matric ecosystem consists of multiple applications written in different languages:

- **matric-cli**: TypeScript (Node.js)
- **matric-memory**: Rust

Both applications need model evaluation capabilities. Currently, evaluation code is duplicated:

- matric-cli has TypeScript evaluation in `source/eval/`
- matric-memory has Rust evaluation in `crates/matric-inference/`

This duplication leads to:
1. Bug fixes applied in one place but not the other (e.g., MBPP function name extraction fixed in commit `51382e2` for matric-cli only)
2. Inconsistent evaluation methodology
3. Duplicated effort implementing the same features twice
4. Different bugs and edge cases in each implementation

We need to choose a primary language for the evaluation core and a strategy for integration with other languages.

## Decision

**Implement the evaluation core in Python with thin subprocess-based bindings for TypeScript and Rust.**

### Architecture

```
                    +-------------------+
                    |   Python Core     |
                    |   (matric-eval)   |
                    +-------------------+
                           |
            +--------------+--------------+
            |                             |
            v                             v
    +---------------+             +---------------+
    |  TypeScript   |             |     Rust      |
    |   Binding     |             |   Binding     |
    | (subprocess)  |             | (subprocess)  |
    +---------------+             +---------------+
            |                             |
            v                             v
    +---------------+             +---------------+
    |  matric-cli   |             | matric-memory |
    +---------------+             +---------------+
```

### Binding Implementation

**TypeScript (npm package)**:
```typescript
import { spawn } from 'child_process';

export async function evaluate(options: EvalOptions): Promise<EvalResult> {
  const args = buildArgs(options);
  const proc = spawn('matric-eval', args);

  return new Promise((resolve, reject) => {
    let stdout = '';
    proc.stdout.on('data', (data) => { stdout += data; });
    proc.on('close', (code) => {
      if (code === 0) {
        resolve(JSON.parse(stdout));
      } else {
        reject(new Error(`matric-eval exited with code ${code}`));
      }
    });
  });
}
```

**Rust (crate)**:
```rust
use std::process::Command;
use serde::Deserialize;

pub async fn evaluate(options: EvalOptions) -> Result<EvalResult, Error> {
    let args = build_args(&options);
    let output = Command::new("matric-eval")
        .args(&args)
        .output()?;

    if output.status.success() {
        Ok(serde_json::from_slice(&output.stdout)?)
    } else {
        Err(Error::ProcessFailed(output.status.code()))
    }
}
```

## Consequences

### Positive

1. **Leverage mature ecosystem**: All major evaluation frameworks (Inspect AI, lm-eval-harness, HELM) are Python-based. We get 100+ pre-built evaluations immediately.

2. **Avoid reinventing the wheel**: Python frameworks already handle:
   - Prompt formatting for different models
   - Code extraction from markdown fences
   - Safe code execution sandboxing
   - Statistical significance calculations
   - Standard benchmark implementations

3. **Single source of truth**: Bug fixes and improvements are made once in Python, automatically available to all consumers.

4. **Simpler maintenance**: One codebase to maintain instead of three (Python, TypeScript, Rust).

5. **Community support**: Python ML ecosystem has extensive community support, documentation, and examples.

6. **Bindings are simple**: Subprocess wrappers are a well-understood, low-maintenance pattern. No FFI complexity.

### Negative

1. **Python dependency**: Applications must have Python installed or use containerized execution.

2. **Subprocess overhead**: Each evaluation invocation incurs process startup cost (~100-200ms). Acceptable for evaluation (minutes to hours) but not suitable for real-time inference.

3. **Cross-language debugging**: Debugging issues requires understanding Python code even when called from TypeScript/Rust.

4. **Type safety at boundary**: JSON serialization/deserialization at language boundaries requires careful type definitions.

5. **Installation complexity**: Users need to install Python package (`pip install matric-eval`) in addition to npm/cargo package.

### Mitigation Strategies

| Concern | Mitigation |
|---------|------------|
| Python dependency | Provide Docker image with all dependencies |
| Subprocess overhead | Batch multiple evaluations in single invocation |
| Cross-language debugging | Structured JSON logging, clear error messages |
| Type safety | Shared JSON schema, generated type definitions |
| Installation | CLI installer script, clear documentation |

## Alternatives Considered

### Alternative A: TypeScript Core

**Description**: Implement in TypeScript, provide Rust bindings via napi-rs or subprocess.

**Pros**:
- Direct integration with matric-cli (no subprocess)
- Type safety in TypeScript ecosystem
- Single JavaScript runtime for web-related tools

**Cons**:
- No access to Python evaluation frameworks
- Must reimplement 100+ benchmarks from scratch
- Limited ML ecosystem support in Node.js
- Rust integration still requires subprocess or complex FFI

**Rejected**: The effort to reimplement evaluation frameworks far outweighs the benefit of native TypeScript integration.

### Alternative B: Rust Core

**Description**: Implement in Rust, provide bindings to Python/TypeScript.

**Pros**:
- High performance
- Memory safety
- Direct integration with matric-memory
- Single binary distribution

**Cons**:
- No access to Python evaluation frameworks
- Rust ML ecosystem is immature for evaluation tasks
- Python bindings via PyO3 are complex to maintain
- TypeScript bindings require wasm-pack or napi-rs

**Rejected**: Rust's ML ecosystem is not mature enough for evaluation tasks. Would require reimplementing all benchmarks.

### Alternative C: Polyglot (Multiple Languages)

**Description**: Maintain separate implementations in each language.

**Pros**:
- No cross-language dependencies
- Native integration in each ecosystem
- Independent evolution

**Cons**:
- Triple maintenance burden
- Bug fixes must be applied three times
- Inconsistent evaluation results across implementations
- Already proven painful (current state)

**Rejected**: This is the current situation that we're explicitly trying to avoid.

### Alternative D: Python Core with FFI

**Description**: Use FFI (PyO3 for Rust, NAPI for Node) instead of subprocess.

**Pros**:
- Lower latency per call
- Direct memory sharing
- No process startup overhead

**Cons**:
- Complex FFI boundary maintenance
- GIL considerations for Rust
- Native module compilation required
- Platform-specific binaries
- Harder to debug

**Rejected**: Subprocess overhead is negligible for evaluation workloads (minutes to hours). FFI complexity not justified.

## Validation

This decision will be validated by:

1. **Prototype**: Implement HumanEval benchmark in Python with TypeScript binding
2. **Metrics**: Measure subprocess overhead vs evaluation time (expect <0.1%)
3. **Usability**: Test binding ergonomics from matric-cli

## References

- [Inspect AI Documentation](https://inspect.aisi.org.uk/)
- [lm-eval-harness GitHub](https://github.com/EleutherAI/lm-evaluation-harness)
- matric-cli TypeScript evaluation: `/home/roctinam/dev/matric-cli/source/eval/`
- matric-memory Rust evaluation: `/home/roctinam/dev/matric-memory/crates/matric-inference/src/bin/eval.rs`
