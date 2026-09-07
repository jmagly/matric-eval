# Consumer migration fixtures

These are hand-authored expectations for #125, not validation results. No project
reader, reducer, converter or trend writer was executed to generate them.
`expectations.json` binds this plan to source artifact bytes using SHA-256.
Existing sibling `v2/` and `trials/` goldens remain unchanged.

The three `legacy-*.json` files deliberately lack observation/comparison evidence.
Zero remains zero and null remains null; neither file is qualified for ranking.
The summary retains distinct full provider/model IDs even when suffixes match.
A numeric historical display is separate from recommendation eligibility.

`strict-json-cases.json` contains input *strings*, including invalid JSON and a
Unicode-escaped duplicate key. Expected JSON syntax acceptance is separate from
consumer-shape acceptance. It must be exercised by both Python and TypeScript;
ordinary last-key-wins parsing cannot establish conformance.

Expected failure codes are the proposed migration profile names. Fixtures do not
claim that these readers or output schemas already exist. Conversion tests must
write into fresh temporary paths and compare hashes of the source before/after.
No golden file is an output path or database migration target.
