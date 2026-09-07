# Restricted generated Python execution

Local Python code and stdin/stdout scorers use the shared isolated execution
runner. A host subprocess is not an execution boundary for generated code.
DS-1000 previously had a separate host execution path. It now returns unscored
`ds1000_profile_unqualified`: the standard-library image does not qualify its
data-science packages or longer task budgets. A dedicated immutable dependency
profile and runtime evidence are required before DS-1000 execution is restored.

The runner refuses execution when its configured Docker backend, pinned image,
or required controls are unavailable. There is no host execution fallback.

## Profile and trust boundary

`python-restricted/1` uses a locally prepared, digest-pinned Python image and
Docker's maintained `runc` runtime with Linux namespaces, cgroup limits, default
seccomp and AppArmor. This profile is a shared-kernel container boundary. It does
not claim resistance to every kernel/runtime vulnerability or qualify a model.
The host administrator, Docker daemon, launcher, image and kernel are trusted.
Keep the host and runtime patched. Docker administrative access is privileged;
only the trusted controller receives it, never generated code.

| Control | Restricted profile |
| --- | --- |
| CPU | One CPU worth of quota |
| Memory | 256 MiB; combined memory/swap also 256 MiB |
| Processes | 32 container tasks |
| Execution wall time | At most 30 seconds; callers may request less |
| Output | At most 64 KiB combined stdout/stderr |
| Input | Bounded serialized code and stdin payload |
| Filesystem | Read-only image; bounded 16 MiB temporary filesystem |
| Identity | Unprivileged UID/GID 65534; all capabilities dropped |
| Privilege | No new privileges; default seccomp and AppArmor |
| Network | None; private container namespaces |
| Host exposure | No host mounts, sockets, devices, GPUs or ambient credentials |
| Lifecycle | Unique container; inspect before start; remove and verify absence |

Memory and swap are intentionally equal to prevent additional swap allocation;
Docker's resource documentation explains the distinction between memory and
combined memory/swap limits. CPU quota limits consumption rather than reserving
a core. See [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).
The default seccomp allowlist is an additional restriction, not a complete
security guarantee. See [Docker seccomp documentation](https://docs.docker.com/engine/security/seccomp/).

## Explicit runtime preparation

Image acquisition is a separate trusted preparation step. The execution path
uses `--pull=never` and requires an immutable `repository@sha256:digest` reference.
Record the image ID, digest, platform, runtime versions and source/lock hashes
with validation evidence. A new image or relaxed benchmark environment requires
a reviewed profile and new qualification evidence.

Set `MATRIC_EVAL_SANDBOX_IMAGE` to the prepared digest reference. Set
`MATRIC_EVAL_SANDBOX_COMMAND` to a JSON argument array when an explicit launcher
is needed. For the authorized A100 environment this is `["sudo", "-n", "docker"]`.
The runner never tries sudo automatically. Do not add model credentials to the
container, launcher arguments or CI. Tests with ordinary mocks do not establish
that the configured runtime enforces these controls.

## Failure and cleanup policy

Every result includes a classified outcome and execution provenance. Scorers
preserve the provenance in native score metadata. Native log artifact references
link result-contract observations back to that evidence.

| Trigger | Behavior | Cleanup / sensitive state | Notification | Recovery |
| --- | --- | --- | --- | --- |
| Backend or image unavailable | Refuse execution; unscored | No generated code starts; no credentials passed | Structured unavailable status | Prepare the configured runtime/image and rerun |
| Invalid configuration or effective policy mismatch | Refuse execution; unscored | Remove any created container and verify absence | Structured policy denial | Correct the configuration; no bypass |
| Controller/daemon fault | Unscored infrastructure failure | Remove exact container; retain cleanup result | Structured infrastructure status | Restore backend health and rerun |
| Wall-time or output bound reached | Stop execution; observed failure only after verified cleanup | Remove container and its descendants | Explicit timeout/output-limit outcome | Treat as the declared task budget outcome |
| Cancellation | Abort execution | Remove exact container in final cleanup | Cancellation propagates | Start a fresh evaluation if desired |
| Cleanup cannot be verified | Unscored infrastructure failure | Report uncertainty; never assert descendants are gone | Cleanup failure in provenance | Operator resolves the identified container/backend before reuse |
| Assertion or output mismatch | Observed incorrect answer | Remove container and verify absence | Normal measured failure | Continue evaluation |
| Missing test harness | Unscored grader failure | No generated code starts | Explicit unavailable-harness reason | Repair benchmark test data |

Killing the Docker client alone does not stop a container. Cleanup must target
the created container and verify its absence. Runtime faults and unavailable
isolation must never become incorrect model answers. No override enables host
execution when a restriction fails.

## Controlled runtime verification

Executable validation for this program runs only on A100, in an isolated checkout
and results directory, following [the A100 policy](../testing/a100-execution.md).
`tests/integration/test_isolated_execution_runtime.py` requires explicit
`MATRIC_EVAL_TEST_ISOLATION=1` and the configured runtime. It covers known correct
and incorrect code, stdin/stdout, host and environment sentinels, restricted
network/filesystem access, bounded output/process fixtures, timeout and cleanup.
Review the controlled fixtures and effective policy before execution. Preserve
initial failures, skips, final command/exit/JUnit evidence and fixture hashes.

## A100 profile evidence

On 2026-09-07, the dedicated `ei-123-isolation` checkout passed nine controlled
runtime probes using Docker 29.7.2, runc 1.4.3, cgroup v2, builtin seccomp and
AppArmor on Linux/amd64. The prepared image reference was
`python@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84`.
Evidence is retained at `/srv/matric-eval/results/ei-123-isolation/`, including
runtime/image inspection, initial refusal on a corrected Docker field-name
mismatch, and the successful `runtime-complete-junit.xml` with payload hashes and
execution provenance. Invalid UTF-8 and actual SIGINT cancellation are covered.
This qualifies the tested controls on that configuration; ordinary CI skips the
opt-in runtime probes and does not substitute for this evidence.

The controller captures at most 64 KiB of raw output and also bounds the UTF-8
encoding of returned text. Replacement/truncation flags and raw captured-byte
hashes make decoding loss explicit. The execution deadline excludes bounded
backend preparation and cleanup calls, each of which has its own timeout.
Scorer assertion execution and stdout comparison retain their existing harness
semantics; container isolation alone does not make a same-process test harness
tamper-proof against generated code.
