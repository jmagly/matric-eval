# Auxiliary client transport conformance

The `matric-eval.client-conformance/1` profile binds the LiteLLM version, public
broker identity/revision and endpoint, model digest and target identity, route,
thinking and tool settings, output cap, and timeout. Any change changes its
fingerprint; prior evidence must not be reused. Model and broker identities must
come from scoped owner evidence, not a guessed model tag. Profile input must not
contain credentials. Credentials remain in the actual client's supported secret
channel and never in receipts.

`qualify_completion` invokes LiteLLM itself with explicit JSON Content-Type and
request ID, zero retries, no streaming, fixed output cap and timeout. The native
profile uses `ollama_chat/` and requires `think:false` on `/api/chat`.
OpenAI-compatible thinking-off is rejected until separately demonstrated. Tool
capability must be exercised with a tool request and a returned call; visible
text alone does not establish support. Embedding consumers must separately use
`validate_embedding` with measured vector and server-attested digest.

Run no-model fixture tests on A100 with LiteLLM 1.81.11 installed. These retain the
original missing-header failure alongside the corrected wire request, hidden
reasoning and empty-output rejection, and lost-ack/admission fixtures that count
actual HTTP attempts. Optional dependency skips are not qualification evidence.

The TAU runner uses the shared argument validation for explicitly provided
arguments. Its existing defaults and frozen external model stay unchanged. This
validation does **not** qualify the existing runner's implicit retry defaults.
Native local simulator qualification is an amendment candidate, not permission
to execute deferred TAU or compare changed simulator protocols as matched runs.

After explicit authorization and scoped allocation, an operator may run:

```sh
python scripts/qualify_auxiliary_client.py --profile PROFILE.json \
  --lease-receipt LEASE.json --receipt NEW-RECEIPT.json --authorized-live-canary
```

The command makes one bounded actual-client call. It emits only a profile hash,
request ID, content-free outcome and allocation artifact hash, with private file
permissions. Correlate that request ID with the broker owner's scoped admission
and execution evidence. Successful client output stays `pending_broker_evidence`;
it is not a live qualification. No command here searches unrelated traffic.

Admission rejections and response timeouts are different failure codes. A client
response timeout without broker phase evidence is explicitly **phase unknown**;
we cannot infer admission wait, warmup, or inference. Wait/yield/resume and
exactly-once broker guarantees remain unsupported. Lost acknowledgments never
trigger application replay. No timeout increase substitutes for measuring phase.

Outstanding qualification gates: authorized live broker correlation, measured
phase durations, broker wait/yield/resume contract, live embedding digest attestation,
and integration of an approved local amendment into scored execution. Transport
correctness does not establish simulator semantics or grader calibration (#126).

`qualify_embedding` also invokes LiteLLM on `/api/embed`; its fixture checks the
actual returned vector dimensions and rejects digest changes before dispatch.
The expected and observed digests must come from independently scoped model and
broker evidence, since an embedding response alone does not carry the digest.

A100 fixture evidence (2026-09-08): Python 3.11.15, LiteLLM 1.81.11; 12 checks
passed in the isolated `/srv/matric-eval/workspaces/issue-159-validation` checkout.
JUnit is `client-conformance-junit.xml` there. Native admission rejection was
wrapped as APIConnectionError(500), with OllamaError(429) in the exception chain;
classification uses the original structured status without parsing error text.
The real OpenAI route omits `stream:false` and relies on the API's false default;
its separate fixture checks that effective behavior and retained reasoning.

Identity review corrections: the live command reads the public model metadata
before and after the client call and rejects a changed/missing digest. Metadata
receipts are explicitly `public_metadata_tag`; they never establish the digest
used by an executing request. Request-bound execution digest evidence still
requires the broker owner's correlated record. Both target and auxiliary names
are normalized across provider prefixes and implicit `:latest` aliases.

LiteLLM 1.81.11 replaces the native response's model with the requested model in
its normalized result. Therefore native qualification uses a per-call HTTP client
response hook to inspect its own raw model field and request options before that
normalization. The hook retains only identity/check outcomes; it neither reads
unrelated traffic nor stores raw message content. The wrong-model HTTP fixture
fails even when the normalized LiteLLM identity appears correct. Tool results
must name a requested function and contain JSON-object arguments conforming to
that function's requested JSON schema. Embedding fingerprints bind broker
identity/revision, endpoint, timeout, dimensions and installed client dependencies.

The dedicated A100 fixture environment currently uses LiteLLM 1.81.11 with
OpenAI 3.9.0, httpx 0.28.1, and Python 3.11.15. This is not the main lockfile
environment and does not qualify the external study runtime. The separately
inspected context-guard and simulator-guard-v3 environments use OpenAI 2.20.0,
httpx 0.28.1, and Pydantic 2.12.4 with LiteLLM 1.81.11. Qualification fingerprints
include installed OpenAI/httpx versions so evidence cannot transfer silently.

The CI transport step now uses the independent locked project in
`tests/profiles/client-conformance/`; it does not change the main package's
OpenAI requirement. On A100 run the same commands:

```sh
uv sync --locked --project tests/profiles/client-conformance
uv run --locked --project tests/profiles/client-conformance \
  python scripts/run_client_conformance_tests.py
```

This profile pins LiteLLM 1.81.11, OpenAI 2.20.0, httpx 0.28.1 and Pydantic
2.12.4 to the inspected incident runtime. All transitive dependencies are locked
from PyPI. The driver verifies these installed identities before collection and
fails on any skipped fixture. It prints inventory and retains JUnit. This is
transport regression coverage, not a substitute for the full external harness
lockfile, live GPU broker evidence, or scored-run qualification.

The CI change adds shell steps to the existing Python 3.11 test job and reuses
its existing pinned artifact action. It introduces no new action, installer or
container reference; existing container/tool pin migration is outside this diff.
