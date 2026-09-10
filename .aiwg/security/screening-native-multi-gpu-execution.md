# Security screening: native 1+ GPU execution

## Protected boundaries

- GPU lease tokens remain private mode-0600 artifacts and never enter public records, logs, CLI output, or tracker comments.
- Exact owner, resource ID, container label, controller identity, and full GPU UUID list must agree before any signal, stop, remove, or release action.
- A set overlap with unresolved prior work blocks acquisition; disjoint sets may proceed only when broker policy permits.
- Inputs accept exact `GPU-*` UUIDs only. Device indexes, `all`, globs, and ambient enumeration are rejected.

## Abuse and failure cases

- Duplicate UUIDs inflating aggregate capacity.
- Requesting the display GPU alongside A100s.
- Substituting a larger visible set after lease acquisition.
- Reordering ranks between protocol, Docker, and CUDA visibility.
- Releasing only a subset after a worker or broker timeout.
- Leaking a lease token through multi-worker environment or error aggregation.

## Gate

No production multi-GPU profile is supported until unit/integration threat cases pass and a content-free Basilisk qualification proves topology, exact visibility, readiness, and set-atomic cleanup.
