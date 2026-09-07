# Role-export expectations

These hand-authored synthetic files are fixture preparation for #129, not a
production manifest schema, executed export or evidence of access qualification.
`inventory.json` records a complete toy inventory; production completeness must
come from the custodian-controlled identity, never this caller-style boolean.
The eventual fixture adapter must construct shared `DataReference` records from
source/row/role/independent-unit fields, retaining the original values.

Each input file contains its displayed sentence followed by one LF. Input hashes
cover exactly those UTF-8 bytes. Record-file hashes include their trailing LF and
are deliberately distinct from an eventual canonical object hash.
`expected-sft.jsonl` has two compact JSON records in the declared order, each with
one LF; JSON input strings preserve their source LF. Outcomes and expected values
were authored without invoking production policy, exporters or reducers. File
hashes were read with the standalone `sha256sum` utility, not project execution.

`expectations.json` lists required reasons rather than an exhaustive ordering of
every possible diagnostic. For example, the final row may also expose the known
cross-role duplicate; it must still be rejected as final-test material. The
approved subset includes exactly train-a and dev-b. Without explicit subset
approval, this mixed request has no materialized output.

The changed-target candidate deliberately changes row ID, target and independent
unit ID, but reuses the held-out input. The cluster peer has distinct input bytes
but shares `unit-c`. Both must reject. None of these exact fixtures proves
near-duplicate coverage or semantic independence.

Selection, withdrawal, orphan and reward cases describe ordered transitions to
exercise after implementation is authorized. Checkpoint names here are fixture
labels only; actual contracts require immutable checkpoint identities. Expected
role/eligibility transitions must not mutate original inventory or quality files.
Fresh-request stable manifests require the same inventory and policy cutoff;
timestamped execution receipts are separate. A changed ledger cutoff is not an
identical authorization input even if the selected plaintext has not changed.

The access test must create an unpredictable sentinel at runtime on A100 and
never pass its value to the worker. This directory intentionally contains no
purported protected sentinel. The #123 Docker profile remains unchanged. A
missing runtime, forged receipt, uncertain cleanup, or mocked read denial cannot
count as successful access qualification. No real private study content, judge
qualification or trained model is represented by these files.
