# Operator-managed deployments

Some matric-eval deployments run on hosts the project does not own. The
reference case is the 3x A100 evaluation host, where the operator holds SSH
access but the hardware belongs to the customer. Those hosts must not carry a
long-lived credential for the canonical git remote, so they cannot `git pull`.

This page defines how such a deployment is updated and how drift is detected.

## Deployment shape

| Item | Value |
|---|---|
| Checkout | `<data-root>/workspaces/matric-eval` |
| Environment | `.venv` in the checkout, editable install |
| Data root | `<data-root>` — `benchmarks/`, `cache/`, `datasets/`, `results/`, `workspaces/` |

The data root is not a git repository. Only the checkout is. Note that the
checkout lives *inside* `workspaces/`, alongside per-run workspace trees; any
reclamation must therefore refuse to remove a version-controlled tree. See
[Resource lifecycle](../testing/resource-lifecycle.md) and
`matric_eval.studies.run_residue`.

## Detecting drift

Run on the deployment host:

```bash
cd <data-root>/workspaces/matric-eval
git log --oneline -1                       # deployed commit
git rev-list --count HEAD..origin/main     # gap, if origin/main is fresh
```

A deployment that cannot fetch will report a stale `origin/main`, so the gap is
a lower bound. Confirm the cached ref is current before trusting the number:

```bash
git log --oneline -1 origin/main
```

## Updating over SSH with a bundle

A git bundle moves history as a single file over an existing SSH session. No
credential for the git host is installed on the deployment, and the transfer is
verifiable before anything is written.

**1. Build an incremental bundle** on a machine that can reach the remote. Use
the deployed commit, or any ancestor of it that is also on `main`, as the
basis so the bundle carries only new objects:

```bash
cd <operator-clone>
git fetch origin
BASIS=$(ssh <host> 'cd <data-root>/workspaces/matric-eval && git rev-parse HEAD')
git bundle create /tmp/matric-eval.bundle origin/main refs/tags/<tag> ^"$BASIS"
```

If `$BASIS` is not an ancestor of `origin/main` — for example the deployment
carries a local commit — use its parent, or the nearest shared ancestor from
`git merge-base "$BASIS" origin/main`.

**2. Ship and verify.**

```bash
scp /tmp/matric-eval.bundle <host>:/tmp/
ssh <host> 'cd <data-root>/workspaces/matric-eval && git bundle verify /tmp/matric-eval.bundle'
```

`git bundle verify` fails when a prerequisite is missing, so a bundle built
against the wrong basis is rejected before it can write anything.

**3. Record a rollback ref, then fetch and check out.**

```bash
ssh <host> 'cd <data-root>/workspaces/matric-eval
  git branch -f pre-update-rollback HEAD
  git fetch /tmp/matric-eval.bundle \
    "refs/remotes/origin/main:refs/remotes/origin/main" \
    "refs/tags/<tag>:refs/tags/<tag>"
  git checkout <tag>'
```

**4. Reinstall.** Dependency floors and entry points change between releases;
an editable install does not pick those up on its own. Capture the current
environment first so the reinstall is reversible:

```bash
ssh <host> 'cd <data-root>/workspaces/matric-eval
  uv pip freeze --python .venv/bin/python > /tmp/pre-update-freeze.txt
  uv pip install --python .venv/bin/python -e ".[dev]"'
```

**5. Verify** before releasing the host back to scheduling:

```bash
ssh <host> 'cd <data-root>/workspaces/matric-eval
  .venv/bin/python -c "import importlib.metadata as m; print(m.version(\"matric-eval\"))"
  .venv/bin/python -m pytest -q tests/unit'
```

Confirm the reported version matches the tag, and that any entry points the
release adds are registered:

```bash
.venv/bin/python -c "
import importlib.metadata as m
print(list(m.entry_points().select(group='vllm.general_plugins')))"
```

## Rolling back

```bash
git checkout pre-update-rollback
uv pip install --python .venv/bin/python -r /tmp/pre-update-freeze.txt
```

## Why not a deploy key

A deploy key on a host the project does not own is a durable credential outside
the project's control, and provisioning one needs the owner's authorization. The
bundle path needs no credential, is auditable as a single artifact, and fails
closed when the basis is wrong. Prefer it for customer-owned hardware; a deploy
key is reasonable only on hosts the project itself administers.
