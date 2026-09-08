# External study run status

`matric-eval study-run supervise PLAN DIRECTORY --timeout SECONDS -- COMMAND...`
starts one external adapter with a private, attempt-specific status directory.
Use an absolute directory. The plan supplies the existing run and attempt IDs;
status is a projection and does not replace the accepted-observation journal.

```json
{
  "run_id": "study-id",
  "attempt_id": "attempt-id",
  "tasks": [
    {"model_id": "source", "suite_id": "terminal-bench", "task_id": "frozen-task-id"}
  ]
}
```

Inspect it with `matric-eval study-run status DIRECTORY`, adding `--json-output`
for the versioned machine-readable document. The atomic `terminal_event` field
is a local event for an operator/monitor to consume; it requires no notification
service. A zero exit without all planned task receipts is a failure, not success.
No task starts merely because the adapter or model server is alive.

Tau and Terminal adapters publish task start and native-result projections only
when the supervisor supplies `MATRIC_RUN_STATUS_DIR`. Zero reward remains a valid
measurement; missing rewards and invalid native results do not become zeros.
The status projection retains existing task names and native evidence digests.
It does not authorize a deferred suite or change its frozen scoring protocol.

Heartbeat age and process identity are separate from task progress. Linux process
identity includes host, boot ID, PID and start ticks. A remote host's activity is
unknown. A confirmed lost supervisor is reconciled once to unknown/cleanup-pending;
a merely stale heartbeat is never proof of death. Reads and writes use atomic
replacement, filesystem synchronization and an interprocess writer lock.

Subprocess output is drained with bounded memory. Diagnostics retain redacted,
truncated stdout/stderr, exit code or signal, reason, actor/stage and exception
chain. Adapter exceptions are retained before the supervisor records the process
exit. Keep the status directory private: redaction is a safeguard, not permission
to print credentials or sensitive benchmark content. Native detailed evidence
stays in the original restricted result directory.

The supervisor stops its own process group, including children of an exited
leader. GPU cleanup is explicitly unverified here: lease/container reconciliation
belongs to the lifecycle contract in #156. A status receipt must never be used
as proof that GPU memory or an owned lease was released. This command is not a
model-service launcher or a scheduling policy.

Executable checks for the active comparison run on A100 under
[a100-execution.md](a100-execution.md). The no-model tests exercise actual child
processes, timeout, SIGKILL, supervisor loss, bounded output, zero-task readiness,
missing receipts, run correlation and the status command.
