# Guidance audit — 2026-09-06

Direction: code-to-docs. Scope: WORKSPACE.md, docs/development/session-init.md;
CONTRIBUTING.md inspected for handoff only.

## Findings and resolutions

1. Medium, fixed: WORKSPACE operator context was a placeholder. Added Python 3.11+
   setup, current commands, source map, validation gates, and canonical delivery.
   Evidence: pyproject.toml, Makefile, src/matric_eval/cli.py, providers/, tasks/,
   core/, state/, studies/, bindings/typescript/, .aiwg/aiwg.config, git remote -v.
2. Medium, fixed: session-init requested an initial Inspect AI prototype and
   scaffold despite those being implemented. Replaced with current-task prompt,
   source-first inspection, real paths and current checks.
3. Medium, fixed: session-init used the older CLAUDE.md startup path and a nonexistent
   root PLANNING.md rather than the WORKSPACE.md then AIWG.md bootstrap. New links follow AGENTS.md.
4. Medium, fixed by root: CONTRIBUTING.md directed clone/issues to the GitHub
   mirror while origin is canonical Gitea. Existing quality gates match Makefile.
5. Low, clarified: config.py coexists with the active config package; guidance
   points to config/settings.py and config/__init__.py for current behavior.

## Validation

- git diff --check -- WORKSPACE.md docs/development/session-init.md: passed.
- Python pathlib check of all local links in edited content: passed. Existing
  generated conditional .aiwg/quickref.json link remains absent (when configured).
- Commands compared directly with Makefile, pyproject scripts and CLI decorators.
- Generated workspace blocks preserved; only the protected operator block edited.
- No implementation changes; source test suite not required for this lane.
