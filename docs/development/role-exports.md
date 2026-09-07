# Synthetic role-controlled SFT exports

The version-1 API records dataset uses and materializes only explicitly permitted
synthetic SFT rows. It does not enroll real datasets, train models, connect to
training providers, qualify judges or change frozen study #114.

`data.roles` uses the existing `DataReference` and `PartitionRole` contract.
Training and development rows require an explicit `sft_export` grant. Calibration
and validation are unsupported; final, restricted, unknown, withdrawn and expired
rows are denied. Human, unknown and judge label origins are retained in dry-run
decisions but unsupported for materialization. A judge calibration hash is
preserved without being treated as approval or mislabeled as unqualified merely
because this export profile is unsupported.

## Private custodian inventory

`SourceVault` opens a local owner-private directory and fixed `inventory.json`.
Directories must be owned by the current UID with no group/other permissions;
source files have the same ownership/private-mode requirements. Nested reads use
directory descriptors and reject symlinks, traversal and nonregular files.
The inventory binds source revision, completeness scope, exact input hashes,
license, consent bytes, access/retention owners, recipient, expiry, permitted
uses, scorer/rubric/calibration identities and enrolled root checkpoint digests.
Every declared input and the consent file are rehashed before decisions. The
caller cannot supply a convenient subset as the trusted inventory.

These are supported local access controls, not administrator-proof custody.
The OS account owning the inventory remains trusted and must retain authority
over its completeness declaration. A manifest cannot prove there is no additional
external holdout. Real records can be represented for dry-run refusals, but this
change authorizes no real-source enrollment or access grant.

Exact checks compare input bytes independently of targets, so changing an answer
does not disguise a held-out prompt. Cluster checks use the shared
`independent_unit_id`. Protected near-duplicate checks use an explicitly declared
NFC/casefold/whitespace-token Jaccard threshold; no default threshold claims
domain validity. If final rows exist and no threshold is supplied, export cannot
claim clearance. Method, threshold and actual candidate-pair count remain in
the export manifest. Exact/lexical checks cannot establish semantic independence.

## Ledger and current authorization

`RoleLedger(vault)` owns a separate fixed `role-use.sqlite` in the vault. It uses
SQLite rollback journals and `synchronous=EXTRA` on the same observed local
Linux/ext4 profile as #124. It records runtime/storage evidence, validates its
inventory binding and event hash chain, and rejects updates/deletes through
supported tables. It does not open or alter recovery journals. Process-exit
fixtures qualify process recovery, not arbitrary power-loss or admin-tamper
resilience.

Ordinary CI on unsupported filesystems uses a private unit-test seam solely for
SQLite transaction semantics, recording the actual storage profile and the lack
of filesystem qualification in JUnit. The child crash fixture uses the same
explicit test seam. Production still rejects unsupported storage, covered by a
separate refusal test. The A100 access fixture uses the actual profile without
that seam.

`checkpoint()` enrolls only inventory-approved roots or children of known
checkpoints. Immutable checkpoint records have separate reward and independent
quality hashes; changing either under the same identity conflicts. Imported
unknown ancestry cannot become a verified root. `record_use(UseRecord(...))`
records rubric discovery, prompt examples, tuning, checkpoint selection, final
assessment and export uses with actual UID/time, input/output hashes, protocol,
policy, candidate/selected checkpoints and roles. These are declarations of use,
not proof that external training occurred. Invalid uses are still recorded as
ungranted when their enrolled evidence must disclose prior exposure.

Final material used for development or selection conservatively discloses the
whole enrolled final inventory to every compared candidate and its descendants.
`untouched()` is explicitly scoped to this synthetic inventory/ledger; external
lineage remains unverified. Selection/disclosure is committed before the caller
receives the receipt. A new run ID cannot erase that history. `disclose()` is a
single-candidate convenience; use `record_use` for actual candidate sets and
policy hashes. A missing convenience-policy hash remains missing.

Real final-test release is unsupported in this first profile. Before any future
owner-permitted plaintext or outcome release, the access owner must approve the
frozen protocol, checkpoint/candidate set, recipient and exact use, and commit
the disclosure record before delivering content. A refreshed holdout requires a
new source, inventory and protocol version, checks against both old and new input
hashes, independent units and declared near-duplicate methods, and retention of
the prior ledger. Renaming an old holdout never restores untouched status. The
current APIs claim only enrolled synthetic inventory/ledger scope; an unrelated
new vault cannot establish global untouched history or absence of prior external
selection. No current command releases real final material.

Withdrawal and expiry are checked before every export and reuse. Publication
commits intent and policy-check receipts, then reacquires a write transaction to
recheck policy, exclusively create and fsync payload/manifest, recheck current
authorization and accept. The transaction serializes accepted publication with
withdrawals. Receipts bind the observed ledger cutoff; stable manifests bind
semantic authorization state separately from execution timestamps. A lost
acknowledgement can reuse verified existing artifacts only while authorization
still holds. Unaccepted files are unreleased orphans and are never overwritten
or promoted on retry. Retain them for owner diagnosis; a fresh authorized request
uses a fresh destination identity.

## Offline commands and API

An owner prepares a private synthetic inventory and its files, then records the
inventory-approved root using a strict `Checkpoint` JSON document:

```bash
matric-eval record-role-use private-vault checkpoint.json --kind checkpoint
matric-eval export-role-sft private-vault request.json --dry-run
matric-eval export-role-sft private-vault request.json --output private-output
```

Both directories must already be private. `ExportRequest` binds ordered rows,
recipient, checkpoint, protocol, requested kind and whether a denied mixed
request may materialize its explicitly approved subset. A changed request under
the same ID conflicts. `record-role-use --kind use` accepts `UseRecord`;
`--kind withdrawal` and `--kind untouched` expose the corresponding ledger APIs.
The CLI prints strict decision JSON without source text. Validation errors are
sanitized. The ledger records hashes, opaque IDs and codes rather than source
plaintext or exception messages.

The actual wire profile is `matric-sft-jsonl/1`. Its JSONL has `input` and `target`
strings; the separate strict `ExportManifest` retains all role/source/policy and
metric-version metadata plus ordered record hashes and the payload hash.
`read_sft_export(manifest_bytes, payload_bytes)` verifies the schema, rows and
hashes. Reading a file validates content; it does not grant current permission to
use it. Independent requests with identical source/policy/selection produce the
same payload and manifest, while ledger receipts retain execution time and actor.
Unknown schemas, duplicate keys and nonfinite JSON reject.

## Access qualification, withdrawal and limits

The opt-in A100 integration fixture reuses #123's container runner unchanged:
UID 65534, no network, no binds, fixed resource limits and verified cleanup.
A random protected sentinel remains only in a host-private temporary directory.
The worker receives permitted synthetic SFT records and the denied path, never
sentinel content. Direct/traversal/symlink reads fail, the SFT round trip matches
exact bytes, and all outputs/audit are checked for leaks. Native profile and
cleanup receipts are recorded. This proves the bounded container fixture, not a
deployed multiuser custodian service. No accounts or services are provisioned.

The inventory names the access/retention owner. Withdrawal blocks future
materialization but cannot recall a recipient's copies or unlearn a trained
model. An owner must apply actual retention/deletion policy to private payloads,
retaining only permitted audit data. Hashes can themselves identify records;
append-only software does not exempt them from deletion requirements. External
deletion/recall acknowledgement and any required ledger rebaselining remain
owner-managed, explicit operations. No automatic destructive cleanup is provided.
