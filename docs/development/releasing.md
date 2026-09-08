# CalVer and release downloads

matric-eval uses **`YYYY.M.PATCH`**. `YYYY` is the UTC year, `M` is the unpadded
month (1–12), and `PATCH` starts at zero and increments for each release within
that month. For example, `2026.9.0`, `2026.9.1`, then `2026.10.0`. The third
component is a release counter, not the day. Tags have a `v` prefix.

This follows the AIWG and Fortemi conventions. Numeric date-based release
segments are supported by the [Python packaging version specification](https://packaging.python.org/en/latest/specifications/version-specifiers/#final-releases).
Stable three-component versions also work with the TypeScript package tooling.
CalVer does not imply SemVer compatibility promises: read compatibility notes
and pin an exact release when reproducibility matters. Result, protocol and
evidence schema versions remain independent of the package version.

## Distribution policy

**Python and npm registry publication is disabled.** There are no uploads to
PyPI, TestPyPI, the Gitea Python index, or the Gitea npm registry. `pip` may still
install a downloaded wheel and its dependencies; package installation is not
registry publication.

The canonical distribution channel is [Gitea Releases](https://git.integrolabs.net/roctinam/matric-eval/releases).
Each release contains wheel/sdist and TypeScript archives, checksums, source
identity, SBOMs, license/vulnerability review and clean-install evidence. A source
version or prepared release note does not establish that a release is available.

## Prepare a version through a PR

```bash
make version-check
make version-bump
# Or choose an explicit, increasing CalVer version:
python3 scripts/release_contract.py bump --version 2026.10.0
```

The bump command updates `pyproject.toml`, `src/matric_eval/version.py`, the
matric-eval entry in `uv.lock`, and the TypeScript package/lock surfaces together.
It does not upgrade dependencies. It rejects inconsistent starting versions and
noncanonical or decreasing versions. The default uses the UTC month, increments
the current month's counter and resets it to zero on rollover.

Add a matching `CHANGELOG.md` section and `docs/releases/VERSION.md`. Open a PR to
`main`; do not force-push or change historical tags. Validate on the authorized
host using [the execution policy](../testing/a100-execution.md):

```bash
uv lock --check
uv sync --locked --extra dev --extra study
make ci
```

Canonical CI also checks the actual wheel import and TypeScript build/tests.
The full main and mandatory client test lanes share the 80% coverage floor.
CLI smoke checks do not load models. Live public benchmark auditing remains a
required check; external rate limiting is a failure to retry, not a successful
source verification. GitHub CI is a mirror and has no release credentials or
publishing workflow.

## Validate a candidate

Manually dispatch `.gitea/workflows/release.yml` at the intended commit. A branch
dispatch builds and retains the candidate bundle without creating a release or
uploading to a registry. The workflow checks synchronized versions, archive
contents, both SBOMs, license policy, vulnerability policy, and clean consumers
on Python 3.11–3.14 before generating the manifest and checksums. A failure keeps
the available diagnostic artifacts and does not publish a release.

## Create a checked tag

After merging, wait for canonical `ci.yml` to pass the exact `main` commit.
Use a clean checkout with no untracked files. Supply `RELEASE_TOKEN` through your
normal secret mechanism; it needs access to the canonical repository and release
attachments, not package registry permissions. Never put it in a command line,
file committed to git, or release notes.

```bash
tools/release/cut-tag.sh 2026.9.0 --check
tools/release/cut-tag.sh 2026.9.0
git push origin refs/tags/v2026.9.0
```

The wrapper requires exact current `origin/main`, matching versions and notes,
successful exact-commit CI, and an unused tag. It creates only a local annotated
tag and respects the maintainer's configured git signing behavior. No signing
key is provisioned and no signature trust guarantee is claimed. The explicit
push starts the release workflow, which requires existing successful CI for that
exact commit. Tags do not duplicate the complete CI suite.

Before building a tagged release, and again before upload, the release helper
checks the canonical origin, remote tag/commit, main ancestry and latest exact-SHA
`ci.yml` run. A newer pending attempt is awaited within a deadline; a failed
attempt or unverifiable source blocks publication.

## Publication and retries

The publisher verifies the local manifest/checksums, then stages a **draft** Gitea
release. It uploads the complete evidence set and verifies remote asset bytes
before making the release public. Partial uploads remain a draft. Existing assets
must match exactly; conflicting bytes are never overwritten. A retry against an
already public release verifies it without changing its notes or assets.

Resume with the **same retained bundle**, source commit and notes. A workflow
rebuild can produce different audit timestamps or dependency evidence; those
bytes must not replace an existing candidate. Retrieve the original bundle from
the workflow artifacts and invoke `scripts/publish_forge_release.py publish`
with its `--artifact-root`, `--bundle`, `--notes`, `--tag` and `--commit`. If an
already published release needs a correction, prepare the next CalVer patch.

## Install verified downloads

Download the bundle from the selected Gitea release, extract it into an empty
directory, and check its contents before installation:

```bash
tar -xzf matric-eval-2026.9.0-release-bundle.tar.gz
sha256sum --check SHA256SUMS
python3 -m venv .venv
. .venv/bin/activate
python -m pip install ./packages/python/matric_eval-2026.9.0-py3-none-any.whl
matric-eval --version
npm install ./packages/typescript/matric-eval-client-2026.9.0.tgz
```

The TypeScript client still requires the Python executable on `PATH`. Preserve
the manifest and evidence when using a release for a study. Registry publishing
would require a separate reviewed change to this policy and the workflows.

The audit requirements export uses `--no-hashes` because pip cannot combine its
hash-checking mode with the study dependency pinned to a Git commit. `--locked`
still preserves exact package versions and the VCS commit; installation uses the
unchanged lock file. This flag applies only to the audit input, not dependency
selection or release installation. A missing, failed, or skipped dependency audit
still blocks release: removing hashes does not waive an unauditable dependency or
any vulnerability-policy finding.
