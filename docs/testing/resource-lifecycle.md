# Study resource lifecycle

`python -m matric_eval.studies.resource_lifecycle run --directory PRIVATE_ATTEMPT_DIR --run-id RUN --attempt-id ATTEMPT --preflight-plan PLAN.json --gpu GPU-UUID --owner OWNER -- docker ...` owns a single labeled Docker container and an exact scoped broker lease. Repeat `--gpu` in CUDA rank order for a multi-device allocation and pass its aggregate `--memory-mib` plus any qualified `--topology-policy`; duplicates, indexes, empty values, and malformed UUIDs fail closed. Use existing journal run/attempt identifiers. The command substitutes `{container}`, `{resource_id}`, and `{ready_base}`. The supported `serve_qwen38_container.sh` uses this controller and requires the run, attempt and resource directory options. The wrapper also requires `--preflight-plan`; the controller executes pre-target qualification in its actual context and revalidates the receipt before acquiring the lease. Resident target checks must pass before `state=ready` is published. Storage admission verifies that Docker's single `device=UUID,UUID` selector exactly matches the ordered lifecycle allocation. Its Python defaults to the checkout `.venv/bin/python`; set `MATRIC_LIFECYCLE_PYTHON` to a qualified environment when appropriate.

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

Acquisition records explicitly distinguish `not-sent`, `unknown`, `rejected`,
and `acknowledged`. The controller persists `unknown` before the broker RPC; its
10-second socket timeout is unchanged. An empty status response cannot discharge
an unknown request: the server may still grant it later. Repeated empty responses,
record age, and a legacy `cleanup=complete` without acquisition/release evidence
are also insufficient. Such records remain pending and block overlapping attempts.
The controller never retries an uncertain acquisition. Reconciliation recovers
only the exact attempt owner's lease, durably records its identity, then releases
it and verifies absence. A confirmed acquisition whose lease is now absent can
complete, including after a lost release acknowledgment. A well-formed synchronous
broker response with `ok=false` plus nonempty `error` and `error_type` is a
terminal rejection acknowledgment; its sensitive details are discarded and the
public record retains only the rejected outcome and time. Reconciliation still
queries exact ownership, so a lease persisted before an error response is recovered
and released. Socket timeouts, disconnects, malformed responses, and incomplete
rejection objects stay `unknown`; an authoritative broker cancellation/outcome
contract is required to discharge those requests when they never produce an
observable lease.

The delayed Unix-broker regression waits through the real socket timeout, returns
an immediately empty status, then grants the request. It verifies pending cleanup,
blocked retry, restart recovery, exact release, idempotence, and token-free public
records. A separate legacy regression verifies that incorrectly completed old
records block new allocation and recover a later grant. Neither fixture loads a
model or requests a real GPU lease.

Admission is revalidated after acquisition, immediately before recording a launch
or opening the launcher dispatch gate. Expiry or changed source/dependencies during
a broker wait prevents target launch and follows the same exact-lease cleanup path.
The 300-second overall admission limit also applies when readiness arrives, in
addition to each check's declared freshness. A 900-second readiness timeout is an
upper timeout, not permission to reuse admission evidence for 900 seconds: readiness
after the admission limit fails target qualification and triggers teardown. The
controller does not automatically refresh evidence or accept new runtime identities
while a target is resident.

## Per-device memory ceiling

A host owner may cap how much of each card a study may use. That cap has to hold
in three places which previously disagreed:

| Place | Before | Now |
|---|---|---|
| Broker lease (`minimum_memory_mib_per_device`) | 75,000 MiB — 91.55% of an 81,920 MiB A100 | derived to stay within the ceiling |
| Model server (`--gpu-memory-utilization`) | protocol value | protocol value, must not exceed the ceiling |
| Observed on the card | never measured | sampled and asserted when the server reports ready |

`matric_eval.studies.device_memory` owns the arithmetic and the assertions so
the three cannot drift apart.

### Declaring the ceiling

```yaml
study:
  execution:
    model_server:
      gpu_memory_utilization: 0.87
      max_device_memory_fraction: 0.87
```

`max_device_memory_fraction` is authoritative. It defaults to
`gpu_memory_utilization`, so an existing protocol keeps its behaviour until the
field is added. Both are validated to `[0.5, 1.0)`, and
`gpu_memory_utilization` may not exceed `max_device_memory_fraction`.

Protocol load also refuses a parallelism profile whose per-device reservation
exceeds the ceiling, so a lease can no longer commit more of the card than
policy allows.

### Why a margin below the host limit

A host limit of 90% should not be declared as `0.90`. The server's
`--gpu-memory-utilization` bounds its own allocator, but not everything resident
for that process — the CUDA context and NCCL communication buffers sit outside
the fraction it profiles, and any sidecar on the same card is not covered at
all. `DEFAULT_DEVICE_MEMORY_CEILING` is therefore `0.87`: on an 81,920 MiB A100
that is 71,270 MiB, leaving roughly 2,458 MiB of headroom under a 90% limit.

### Evidence

When the server reports ready, each leased device is sampled and the run fails
closed if any card is above the ceiling. The server receipt carries the reading:

```json
"device_memory": {
  "ceiling_fraction": 0.87,
  "devices": [{"uuid": "GPU-...", "total_mib": 81920, "used_mib": 68000, "used_fraction": 0.830078}],
  "high_water_uuid": "GPU-...",
  "high_water_fraction": 0.830078,
  "high_water_used_mib": 68000
}
```

That turns "we configured a ceiling" into "we measured the cards and here is the
high-water mark", which is what a host owner can actually audit.
