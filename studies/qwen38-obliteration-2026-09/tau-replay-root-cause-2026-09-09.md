# Tau replay sandbox root cause and restart plan

Date: 2026-09-09  
Issue: #154  
Disposition: **go for bounded source-model admission; no-go for paired replay until admission evidence passes review**

## Scope

This record explains the r6 banking sandbox failure without reinterpreting prior model results. The diagnosis used no GPU, did not read or publish lease credentials, and preserved every earlier replay directory. It applies to the pinned local Tau integration only; it does not establish an upstream Tau defect.

## Retained diagnosis

The pinned `@anthropic-ai/sandbox-runtime==0.0.23` creates two Unix-domain bridge sockets under Node's effective temporary directory. Linux permits 107 pathname bytes before the terminating null byte.

The r6 service set `TMPDIR` to its evidence directory. The resulting longest bridge socket pathname was 109 bytes. In that environment the minimal `SandboxManager.run_command("printf sandbox-canary")` returned exit code 1, empty stdout, and the bounded diagnostic `Failed to create bridge sockets after 5 attempts`.

Controls separated the path defect from the sandbox policy and dependencies:

- the same pinned Python and npm environments passed from `/tmp`;
- the same command passed under umask `0077` with a short private `/srv` temporary directory;
- the short-path command also passed as a transient system service running as the study operator;
- both passing controls returned exit code 0, exact stdout `sandbox-canary`, and empty stderr;
- `srt`, `rg`, `bwrap`, and `socat` resolved, and the pinned sandbox/runtime versions matched.

The cause is therefore the r6 temporary-path layout. AppArmor, bubblewrap isolation, package versions, disk space, and the banking task were not the failing condition in this reproducer.

## Repair and regression boundary

The repaired supervisor uses a private attempt-specific directory below `/srv/matric-eval/runtime-tmp`, validates the predicted bridge pathname against the 107-byte limit before starting SRT, and removes only that exact directory during final cleanup. Evidence remains under the immutable replay directory; runtime scratch data does not.

`preflight_qwen38_tau.py sandbox` now runs three times with the actual supervisor environment before any model service or GPU lease is requested. Each receipt includes the path-length budget, resolved dependency identities, and execution result. The production Tau runner uses the same check, so direct invocation also fails early with a typed, content-free path-budget error.

No sandbox control, namespace, AppArmor rule, dependency pin, or task/manifest integrity check is weakened. Upgrading sandbox-runtime is unnecessary for this defect and remains outside this repair.

## On-host target-independent verification

The repaired code was transferred as a sealed Git revision to a fresh Basilisk worktree and exercised through transient system services with umask `0077`. A first integration attempt exposed that the pinned Tau venv does not include the project's application configuration dependency; the sandbox check was therefore made a standalone stdlib-only entry point rather than mutating that venv.

The final service-environment evidence passed:

- sandbox execution: 3/3, identical receipt SHA-256 `5131516f5263db7ae39a5f5cf634cd68eaf8d9be0b383272cfddf83b41a20992`;
- simulator/interface guard: 3/3, identical receipt SHA-256 `bae85273dc57d1299af65d411e5fb4d70c03bb779483a7e02adda030ef69e16e`;
- target context guard: 3/3, identical receipt SHA-256 `39da20352c6ec10a0dd17a5040ea50cf527cad0df5d71b475291c4f9735649c6`;
- Terminal runtime guard: 3/3, identical receipt SHA-256 `041de82a969da1243d7525fe4cb1e9a71a58531a05b7e0deb0f017d815e6faf4`;
- native local simulator/embedding client: passed, receipt SHA-256 `edf854cc36ae101cd484c65d150142a3e4bacae2171945f090953dc08bf3d755`.

The sandbox receipts report a 44-byte temporary directory and a 79-byte longest predicted bridge socket, leaving 28 bytes below the enforced Linux limit. These checks acquired no GPU and started no target-model service.

## Reviewed restart gates

1. Merge the repair after focused and full CI pass.
2. On Basilisk, run the three target-independent sandbox, simulator-interface, context, and Terminal runtime canaries under the short private service `TMPDIR` before model allocation.
3. Load only the source BF16 model and run exactly these manifest members in their declared order:
   - `banking_knowledge:task_021`
   - `airline:3`
4. Invoke `run_qwen38_tau.py` with one `--diagnostic-id` per member. The receipt must declare `diagnostic-subset`, `official_comparison: false`, two parseable results, and `analytic_status_counts: {valid: 2}`. Task reward may be zero; infrastructure invalidity may not be represented as task failure.
5. Stop the source container, confirm its scoped lease is absent, and retain only content-free hashes/status outside the protected evidence store.
6. Review the admission receipt. The paired supervisor independently rejects a missing, reordered, malformed, invalid, or non-diagnostic receipt before GPU allocation.
7. Only after that review may #114 schedule the source/E03/Pliny paired diagnostic replay. Prior r1-r6 evidence remains immutable and outside the new denominator.

## Decision

The sandbox research spike is resolved and the target-independent restart path is qualified. A bounded two-trajectory admission run is approved by this plan once the repair is merged. The full paired replay remains no-go until that admission receipt and cleanup evidence exist.
