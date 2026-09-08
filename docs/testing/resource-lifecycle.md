# Study resource lifecycle

`python -m matric_eval.studies.resource_lifecycle run --directory PRIVATE_ATTEMPT_DIR --run-id RUN --attempt-id ATTEMPT --preflight-plan PLAN.json --gpu GPU-UUID --owner OWNER -- docker ...` owns a single labeled Docker container and an exact scoped broker lease. Use existing journal run/attempt identifiers. The command substitutes `{container}`, `{resource_id}`, and `{ready_base}`. The supported `serve_qwen38_container.sh` uses this controller and requires the run, attempt and resource directory options. The wrapper also requires `--preflight-plan`; the controller executes pre-target qualification in its actual context and revalidates the receipt before acquiring the lease. Resident target checks must pass before `state=ready` is published. Its Python defaults to the checkout `.venv/bin/python`; set `MATRIC_LIFECYCLE_PYTHON` to a qualified environment when appropriate.

No transient systemd unit is created; retained failed unit names cannot collide with this process controller. Inherited run status receives a correlated resource-record link and cleanup state.

Every attempt must have a fresh private directory beneath the same allocation root. An unresolved record on the same GPU blocks later acquisition under that root. Both controller and reconciler take an exclusive attempt lock; simultaneous reconciliation of a live controller fails instead of guessing ownership. Controller subprocess dispatch uses a pipe gate so the durable PID identity is written before execution.

The public record binds owner, run, attempt, unique container/readiness identities and the explicit process-controller type, boot identity and GPU UUID. Tokens are stored separately with mode 0600 beneath the mode 0700 directory. The container is retained until cleanup proves it stopped; the controller never uses Docker `--rm`. CUDA ownership is captured from per-process GPU telemetry and the exact container cgroup. Cleanup stops the process group, stops the labeled container, verifies no remaining owned cgroup processes/CUDA allocations, releases the matching lease, verifies broker absence and removes the stopped container. It never prunes other resources or treats free VRAM as proof of cleanup.

After a controller crash, run `python -m matric_eval.studies.resource_lifecycle reconcile --directory PRIVATE_ATTEMPT_DIR` on the owning host. It recovers uncertain acquisition by the attempt-unique broker owner. Broker outages, changed token/scope, ambiguous ownership, unexplained container disappearance and live CUDA allocations retain `cleanup-pending`. A repeated successful reconciliation is safe. A changed boot permits recovery of absent prior-boot processes; broker ownership must still be checked. Readiness uses the new attempt's path and lease digest; old attempt files cannot qualify a new load.

Do not copy `lease.private.json` or token-bearing readiness filenames to public artifacts. `record.json` is the sanitized resource receipt. This is a resource registry, not an observation journal. Frozen benchmark inputs and evaluation acceptance remain in the existing journal/protocol contracts.

Qualification uses A100 infrastructure. Unit fixtures cover lost acquire acknowledgment, broker outage/reconnect, exact ownership, CUDA release ordering, unrelated resources, pending allocation and repeated attempts; real Unix-socket transport verifies errors do not expose tokens. The retained on-host receipt separately records the bounded real CUDA qualification. Full pipeline qualification additionally needs the staged preflight and scheduler integrations.

Reconciliation enumerates the launcher's entire process session, including members
left behind after its leader exits. Every member must retain the attempt's
`MATRIC_RESOURCE_ID`; an unknown/reused group remains cleanup-pending without being
signaled. Signals use Linux pidfds plus process-start identity checks, so PID reuse
cannot redirect a signal. TERM/KILL escalation is bounded, all observed launcher
PIDs join the CUDA-release predicate, and the session must be extinct before the
owned container is stopped and the lease released. The same path handles normal
controller shutdown and restart reconciliation.

Docker list/inspect/stop/remove and NVIDIA process queries each have a 30-second
subprocess deadline. Timeout preserves the cleanup record and private token;
reconciliation can resume after the service recovers. Real orphan-process and
hung-tool fixtures verify these boundaries on A100 without allocating a GPU.

Acquisition records explicitly distinguish `not-sent`, `unknown`, and
`acknowledged`. The controller persists `unknown` before the broker RPC; its
10-second socket timeout is unchanged. An empty status response cannot discharge
an unknown request: the server may still grant it later. Repeated empty responses,
record age, and a legacy `cleanup=complete` without acquisition/release evidence
are also insufficient. Such records remain pending and block overlapping attempts.
The controller never retries an uncertain acquisition. Reconciliation recovers
only the exact attempt owner's lease, durably records its identity, then releases
it and verifies absence. A confirmed acquisition whose lease is now absent can
complete, including after a lost release acknowledgment. Generic broker errors
remain ambiguous because the protocol does not establish that they precede all
side effects; an authoritative broker cancellation/outcome contract is required
to discharge a request that never produces an observable lease.

The delayed Unix-broker regression waits through the real socket timeout, returns
an immediately empty status, then grants the request. It verifies pending cleanup,
blocked retry, restart recovery, exact release, idempotence, and token-free public
records. A separate legacy regression verifies that incorrectly completed old
records block new allocation and recover a later grant. Neither fixture loads a
model or requests a real GPU lease.
