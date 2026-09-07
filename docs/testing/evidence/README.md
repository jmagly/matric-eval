# Historical #128 skip evidence

This artifact reconciles every skipped testcase in the retained A100 full-suite
JUnit for source `be8e9886f6ff82c5503e6ac890d278751bd16085`. It is evidence about
that #128 source, not a #130 run or a general capability qualification.

[ei-128-skip-dispositions.json](ei-128-skip-dispositions.json) retains all 321
unique skipped node IDs and their actual JUnit reasons. Each record's `policy_id`
resolves to its capability, accountable role and promotion condition in the
`policies` object. No reasons are unmapped. The distribution is 301 missing-data
cases, 9 opt-in isolation probes, 7 unconditional inference/model cases, and 4
unconditional historical-data cases. These are unqualified capabilities in this
run, even when another separately attested profile has executed related probes.

The complete JUnit contains 2,807 cases: 2,486 passed and 321 skipped, with no
failures or errors. The full CI log records 81.53% aggregate coverage. These
counts describe this specific retained run; they are not current test targets.
Exact process exit code was not serialized in these files, so the artifact leaves
that field null rather than inventing a receipt. A passing terminal summary and
orchestrator process status are distinct evidence.

Source, lock, environment, inventory, JUnit and full-log references/digests are
included in the JSON. Full artifacts remain on A100 under
`/srv/matric-eval/results/ei-128-overlap/`; this small checked-in derivative does
not replace them. The environment receipt identifies Python 3.11.15 on basilisk
and lock SHA-256 `b9cd2c3940ab85832e3e30ddd714982c11320bcd82e8554114be84cc86e3a253`.
No human approval, live-model qualification or publication is claimed.
