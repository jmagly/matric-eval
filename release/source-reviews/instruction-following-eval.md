# Instruction Following Eval: scoped source review

Reviewed **2026-09-09 UTC**, expiring **2026-10-09**. This review accepts only
`instruction-following-eval==0.1.0` from
`https://github.com/josejg/instruction_following_eval.git` at
`0c495b2f95155e8b10acb919ae283bfb4d5be6e2`, with the six installed payload hashes
in [the machine receipt](instruction-following-eval.json). It is separate source
review evidence for a distribution unavailable on PyPI, not a successful PyPI
vulnerability scan. Preserve the original pip-audit skip diagnostic.

The A100 review verified the installed noneditable `direct_url.json` commit and
all package bytes against Git's tracked source, including the bundled JSONL data.
The twelve tracked files are hashed separately; aggregate payload identity is
`fd8cea5320c97129bbdd0f5d431326a9cadeca9230e8adefa506fdb5dd71eaa4`.
The build is declarative `setuptools.build_meta`, without a custom setup script.
All runtime modules were read; AST call inventory additionally covers upstream
test files. Constants and JSONL records are data. No response-controlled eval,
exec, subprocess invocation, dynamic import or filesystem pathname was identified.
This is a bounded review, not proof that no vulnerability exists.

Bandit **1.8.6** scanned 3,108 runtime lines without exclusions or scan errors.
Its nonzero exit and all **28 low-severity findings** are retained:
25 B311 uses generate random benchmark defaults, not cryptographic secrets;
three B101 assertions check response types, not authorization. These findings
were resolved by context review, not hidden or patched. There were no Bandit
medium/high findings. The raw report and call inventory accompany the receipt.

The [OSV commit query](https://api.osv.dev/v1/query) returned HTTP 200 and `{}`.
That means no indexed match was returned; OSV does not establish that this fork
or commit is covered. The repository's [public advisory page](https://github.com/josejg/instruction_following_eval/security/advisories)
showed no published advisories. Neither observation substitutes for source review.
The exact commit includes an [Apache-2.0 license](https://raw.githubusercontent.com/josejg/instruction_following_eval/0c495b2f95155e8b10acb919ae283bfb4d5be6e2/LICENSE),
whose hash is bound in the receipt.

The accepted usage is Inspect IFEval with trusted pinned instruction metadata,
bounded model responses, and **NLTK 3.10.3**. Concrete limitations remain:

- `evaluation.py:16–35` downloads unpinned `punkt` and `punkt_tab` resources when
  absent. Inspect's IFEval scorer calls this helper. This receipt does not attest
  those external resource bytes; preprovision and review them separately for
  offline or reproducible studies.
- `instructions_util.py:1660` names `english.pickle`. The installed NLTK 3.10.3
  implementation redirects that exact path to its pickle-free tokenizer before
  opening it. A bounded monkeypatch check verified the control flow without
  resource downloads. This conclusion does not extend to other NLTK versions.
- Several regex patterns interpolate instruction kwargs. These are trusted
  benchmark metadata, not response text. Arbitrary user-controlled metadata and
  unbounded hostile workloads are outside the accepted scope. The evaluator
  itself provides no response-size, CPU or memory limit.
- Language detection failures can log full responses and return true. Responses
  and logs must not be assumed secret-safe; evaluation scores are not security
  decisions. Benchmark correctness/reproducibility concerns remain distinct from
  this source review.
- Build-tool and transitive dependency vulnerabilities remain separate release
  gates. This review does not waive any indexed vulnerability or other skipped
  dependency. No full fuzzing, regex-complexity proof, upstream functional suite,
  NLTK download or model scoring was performed.

The executable fixture also checked that Python execution syntax in a model
response remains ordinary string data. Raw evidence was generated under
`/srv/matric-eval/workspaces/ifeval-source-review-20260908` on A100. Changing the
commit, installed payload, NLTK version, input trust boundary, or expiry requires
re-review. The distribution is not approved as an arbitrary-input network service.
