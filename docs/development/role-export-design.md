# Dataset role use and export enforcement

Status: reviewed design for
[#129](https://git.integrolabs.net/roctinam/matric-eval/issues/129). The #124 engine
predecessor has merged; the bounded synthetic implementation and its actual
limits are documented in [role-exports.md](role-exports.md). No real-data access
grant or training is implied. #126's merged calibration contract remains the
qualification authority; this first export profile refuses judge materialization
and preserves its supplied identities without claiming qualification. The
implementation baseline is `0c87cdf`.

## Scope and reuse

Use `results.contract.PartitionRole` and `DataReference` directly: development,
validation, calibration, final_test, training, unknown. Do not introduce a second
partition enumeration. Rubric discovery, prompt examples, tuning, checkpoint
selection, assessment and export are *uses* of data; restricted access is an
access policy, not another partition. Preserve original roles in immutable source
records even when later use disqualifies an untouched-holdout claim.

New code should be confined initially to `src/matric_eval/data/roles.py`,
`role_ledger.py`, `access.py` and `exports.py`, with small CLI command wrappers.
`results/contract.py` remains authoritative for shared identities.
`models/spec.py` supplies checkpoint/intervention identities; model display names
cannot replace immutable revision/artifact identity. New study manifests may
reference the role-manifest and use-ledger receipt hashes without modifying
`studies/protocol.py` selection semantics or #114's frozen manifests.

There is no training engine, provider connector, training upload, paid call or
new benchmark wave. A provider-neutral synthetic export round trip establishes
format conformance only. Real sensitive source enrollment and holdout access
require the named data owner's authorization and an actual access deployment.

## Immutable records and mutable eligibility

Propose a strict version-1 `RoleManifest` containing source revision, canonical
content hash, input-only exact hash, `DataReference`, license/consent
references, source owner, access-policy identity, retention/withdrawal rules and
permitted uses. Canonical content rules are profile-versioned; file-byte hashes
remain distinct from normalized duplicate-detection hashes. Missing source,
cluster, license or access evidence cannot be filled from a display row ID.
The cluster boundary is the existing `DataReference.independent_unit_id`, not
a competing field. Bind the custodian-owned inventory identity and completeness
cutoff: a caller-selected subset cannot establish absence of held-out matches.

Each `UseEvent` records stable request ID, authenticated actor principal,
timestamp, use kind/purpose code, protocol/model/checkpoint lineage, input and
output hashes, policy version, and outcome/reason codes. The ledger contains no
prompts, answers, critiques, labels, unrestricted free-text explanations, tokens,
absolute private paths or raw exception messages. Use opaque artifact IDs;
content hashes can still be identifying and the ledger remains access-controlled.

Use a separate SQLite role-use ledger, borrowing reviewed transaction patterns
from #124 without changing its observation journal. Intent, disclosure/acceptance
and terminal failure are append-only records; identical request/content is
idempotent and different content under the same request ID conflicts. Database
permissions and the custodian-owned local process own writes. An SQL trigger or hash chain
detects accidental edits through supported APIs; it does not make a database
tamper-proof against its administrator. Retain verification/backup receipts under
separate owner-controlled storage when stronger audit assurance is needed.

An eligibility query joins the original manifest, protocol-scoped ledger prefix,
withdrawals and access-policy revision. It never changes the historical
`DataReference.role`. A final holdout used for tuning, prompt construction or
checkpoint selection is disclosed development evidence for that selection
lineage and subsequent descendants. The prior final assessment remains a
historical result; subsequent selections cannot call that holdout untouched.
This scope follows actual model/checkpoint lineage, not just a caller's new run ID.
Missing lineage or ledger continuity yields unknown eligibility, not untouched.

## Access profile with an actual operating-system boundary

The finite first profile reuses #123's existing Docker isolation profile
unchanged: UID 65534, no network and no bind mounts, with its existing resource,
output and cleanup restrictions. A protected synthetic sentinel remains in a
host-private temporary directory and is never mounted or sent to the worker.
Only approved synthetic SFT records enter through bounded input. This is a
controlled container access fixture, not a deployed multiuser custodian service.
No new accounts, services or sandbox permissions are introduced. Host OS identity
identifies the local actor; a JSON `actor` string is not authentication.

The custodian approves a bounded request by immutable manifest, use, recipient,
protocol and expiry, then materializes only authorized records. Library APIs
accept handles beneath configured roots, reject traversal/symlink escapes and
nonregular files, and hash from opened descriptors to avoid checking one file
and reading another. Output is exclusive and private by default; permissive
umask must not create world-readable artifacts. Diagnostics contain reason codes
and opaque IDs, never denied content. Same-user directory checks are useful
guards but do not demonstrate a holdout access boundary.

The A100 fixture verifies actual profile and cleanup receipts and attempts direct,
traversal and symlink reads of the unavailable host sentinel from that worker.
It checks that no sentinel bytes leak through payload, manifest, audit, stdout
or stderr while the permitted synthetic export round trip succeeds. Missing
runtime/profile evidence or uncertain cleanup fails qualification; mocking
`PermissionError` is not equivalent evidence. Real actor identities, retention
owner and protected source paths remain owner-supplied configuration, not a
claim that this fixture deploys custody for real holdouts.

## Final release, selection and crash behavior

The custodian's final-release request names a frozen protocol, model/checkpoint
set, recipient, permitted assessment, and release version. Commit a conservative
disclosure event before providing any plaintext or selection-relevant final
outcome. A crash after commit but before delivery may overstate disclosure; it
must not understate it or permit a later untouched claim. A lost acknowledgement
reuses the original request ID and does not erase the event.

Final outcome access for checkpoint selection records an explicit selection-use
event before returning outcomes. If outcomes were obtained outside the managed
boundary, an owner-entered retrospective disclosure event records that limitation;
the tool cannot prove absence of external access. Refreshed holdouts require a
new immutable source/manifest/protocol version, documented split/cluster checks
and owner release approval. Renaming the old holdout is not refreshment.

## Export policy and stable format

Freeze `matric-sft-jsonl/1` as a local provider-neutral SFT input/target
JSONL profile. Preference and reward materialization are unsupported and reject
explicitly. No hosted API format is assumed.

The stable manifest includes ordered record hashes, source/role/cluster lineage,
license/consent/policy identities, scorer/rubric versions, calibration identities
where applicable, checkpoint lineage, duplicate-check profile/results and export
format. Fix canonical serialization and ordering. Execution receipt actor/time,
request ID and local output path are separate from stable manifest content.
Identical inputs and policies produce byte-identical payload/manifest content;
each actual execution still has its own durable receipt. Write new artifacts
exclusively, never overwrite source or previous exports.

For a mixed-role request, produce an explicit per-record decision plan. Only
eligible training/development records with permitted export use may materialize;
final_test, restricted, unknown, withdrawn or conflicting split records are
rejected with codes. Calibration and validation roles are unsupported in this
first profile, even with a declared grant; final/restricted/unknown roles deny. A
partial export is allowed only when the request explicitly accepts the reviewed
eligible subset. Otherwise any rejection fails the export as a whole. Dry run
records requested uses and decisions without plaintext output or fabricated
successful materialization.

Publication follows committed intent, transactionally checked policy/disclosure,
exclusive fsynced payload and manifest, then terminal receipt. Bind the checked
inventory and role-ledger prefix/cutoff to the authorization transaction. Check
withdrawal and expiry before every materialization or idempotent reuse decision;
an old success receipt does not authorize release after revocation. Serialize
publication authorization against withdrawal and recheck before terminal release.
An orphan artifact remains unreleased pending reconciliation: retries neither
overwrite it nor release it under revoked policy. If artifact hashes match a
prior attempt, recovery still requires current authorization. Filesystem and
ledger operations are not one atomic transaction; crash fixtures must cover each
boundary, including payload-created/terminal-missing and concurrent withdrawal.

Judge-generated targets/preferences/rewards require actual applicable qualified
calibration evidence bound to judge/configuration/rubric/domain and the permitted
use. Consume #126's validated evidence and scope; do not trust a supplied status
string or the existence of a calibration hash. Synthetic calibration never
qualifies a production judge. Deterministic human-authored synthetic SFT fixtures
need no invented judge qualification. Scorer validity and data-use consent are
independent checks, and both must pass where applicable.

## Duplicate, cluster and optimization boundaries

Check source identity, complete-record hashes and input-only exact hashes against
the custodian-owned complete split inventory before export. Changing a target
must not hide reuse of a held-out input. A duplicate spanning final and development/training is a
hard conflict, even under different row IDs. Shared independent-cluster IDs
crossing those boundaries also conflict; rows from one problem, conversation or
document are not independent merely because they have different samples.

A versioned normalized-text/shingle check may report suspected near duplicates,
with normalization, threshold, candidate coverage and method limits retained.
It cannot establish semantic independence or prove absence of contamination.
Unresolved suspicious cross-split matches block release until an owner-reviewed
decision or refreshed split; do not invent universal numeric thresholds. Hash
indices supplied by the custodian can detect protected exact matches without
releasing plaintext. If a required protected near-duplicate check cannot be run
inside the custodian boundary, record it unavailable rather than exporting the
holdout to run the detector.

Use distinct typed `reward_evidence` and `independent_quality_evidence` fields.
Quality references remain read-only evaluation artifacts with their original
metric, scope and eligibility. Selection events record candidate checkpoints,
selected checkpoint, policy, reward objective, and data/outcomes used. A higher
reward never overwrites quality, establishes independent improvement, or restores
holdout eligibility after selection. Imported unknown checkpoint lineage remains
unknown rather than asserted as a verified intervention.

## Withdrawal and retention

The deployment configuration must name the data access/retention owner and
recipient obligations before non-synthetic materialization. Withdrawal appends
an event and blocks future use; it does not silently alter historical ledger
records. Maintain an owner-controlled reverse index of dependent export hashes
to identify affected recipients/checkpoints. Delete protected payload copies
under the actual retention policy and retain only the legally permitted minimal
audit identifiers. Hashes may themselves require removal or protected retention;
append-only software is not an exemption from deletion obligations. Record a
tombstone and reestablish the governed ledger baseline if audit data must be
removed. Offline exports cannot guarantee recall, deletion by a recipient, or
unlearning of an already trained model; report acknowledgement status honestly.

## Fixtures and staged delivery

Hand-author `tests/fixtures/data/roles/` expectations independently of export
implementation. No real #114 source data enters the fixtures.

| Fixture | Expected evidence |
| --- | --- |
| Mixed permitted, restricted, final, unknown and withdrawn rows | Only explicitly approved subset can materialize; rejection codes and original roles retained. |
| Exact duplicate with renamed IDs or changed target; shared cluster with different text | Input-only hash and shared independent-unit boundary reject; incomplete caller inventory cannot establish clearance. |
| Near-match and unavailable protected check | Method limits/unavailable state retained; no proven-independent claim. |
| Final selection then descendant checkpoint claim | Committed selection-use event permanently invalidates subsequent untouched claim for that lineage. |
| Crash/lost acknowledgement during release | Disclosure precedes payload; idempotent request cannot erase history. |
| Real denied OS read, traversal and symlink sentinel | No sentinel bytes in output, audit, stdout or stderr; access boundary actually enforced. |
| Stable synthetic SFT export and import | Identical canonical payload/manifest hashes; separate execution timestamps; no network. |
| Unqualified/mismatched/synthetic judge evidence | Judge-derived export rejects without reinterpreting qualification. |
| Reward update and checkpoint selection | Original independent quality artifact/hash unchanged. |
| Existing output, conflicting request identity, withdrawal/expiry before retry | No overwrite; prior success cannot bypass current authorization; ledger cutoff is transactionally bound. |
| Orphan payload or withdrawal during publication | No terminal release under revoked policy; actual fsync/transaction boundaries reconciled. |

The reviewed scope can be delivered in one bounded implementation PR after
#124 and explicit parent authorization: strict contracts, append-only ledger,
dry-run policy fixtures, synthetic SFT export/import and the unchanged #123
container access fixture. No mandatory multi-PR split is imposed.
A100 validation records source/lock/fixture hashes, command/exit/JUnit output,
initial failures and any unqualified deployment evidence. Real enrollment,
training connectors, calendar retention choices and new final release are
separate owner decisions; this design does not grant them.
