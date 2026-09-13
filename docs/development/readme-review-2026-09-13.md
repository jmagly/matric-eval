# README review — 2026-09-13

## Scope and reference

Reviewed the matric-eval README against the local AIWG README at commit `8ef1115cf`
(`/home/roctinam/dev/aiwg/README.md`). The matric-eval review started from commit
`4c59b18`. This is a documentation and artwork change; runtime code is unchanged.

AIWG's useful editorial pattern is a clear introduction, audience and problem framing,
readable building blocks, task-oriented entry points, practical examples, deeper capability
explanations, and grouped documentation routes. The revision applies that pattern to
matric-eval's implemented evaluation workflows, retaining the project's setup and support boundaries.

## Findings and changes

| Finding | Impact | Resolution |
|---|---|---|
| Introduction moves directly into installation and command inventory | Readers have little help deciding which workflow fits their task | Added audience routes, three problem explanations, building blocks, and workflow selection |
| Quick start suggests recommendations from a default legacy smoke run without a policy | Example does not satisfy current qualified recommendation requirements | Kept the first run bounded; moved recommendations to a dedicated section with policy and eligibility requirements |
| TypeScript example repeats the unsupported recommendation shortcut | Application readers could copy the same incomplete flow | Replaced it with the implemented versioned `evaluate` call and linked the comparison requirements |
| Versioned results and history are missing | Readers cannot discover named metrics, nullable outcomes, strict readers, or migration | Added result inspection, conversion, immutable history, and comparison-scope explanations |
| Study section implies only four commands exist | Status and supervision are undiscoverable | Described the four starting commands and linked the `study-run` group |
| Agentic pipeline is missing | Platform evaluations appear indistinguishable from direct endpoint runs | Added platform inventory, pinned configuration, execution bounds, outcomes, and workflow links |
| Custom-data YAML expects different fields than the preceding JSONL | Copying both snippets produces an inconsistent example | Made field mapping match the sample and explained alternate source field names |
| Internal links point at the GitHub main branch | Canonical-forge and feature-branch readers leave their checkout's documentation | Converted repository documentation links to relative paths |
| No visual introduction or art options | README lacks the visual treatment of its reference | Generated six distinct raster hero directions, retained originals and prompts, and added a gallery |

## Source checks

- [CLI implementation](../../src/matric_eval/cli.py): result format, reader and migration commands,
  recommendation policy ingress, provider inventory, and study command registration.
- [Consumer migration guide](consumer-migration.md): eligibility, aggregation, legacy imports,
  nullable results, and immutable history.
- [Trend store](../../src/matric_eval/trends/consumer_store.py): imports require an individual
  version 2 result envelope; a summary collection is not accepted. The final example names a
  per-model artifact explicitly.
- [TypeScript client](../../bindings/typescript/src/client.ts): `evaluate` overloads,
  version selection, and `loadResult`.
- [Agentic pipeline guide](../testing/agentic-pipelines.md): configuration, discovery,
  execution limits, and quality/infrastructure outcome separation.
- [Package metadata](../../pyproject.toml) and [workspace guidance](../../WORKSPACE.md):
  Python requirement, current source version, installation, and delivery boundaries.

## Artwork

Six separate built-in image generation calls produced six original 1983 × 793 PNGs:
precision instrument, Swiss editorial, paper sculpture, engineering blueprint, retro terminal,
and orbital observatory. All are saved in [the gallery](../assets/readme/README.md), with
[the exact prompts](../assets/readme/prompts.json). Visual inspection checked title spelling,
legibility, wide composition, and distinct media. Illustrative charts and apparatus do not
represent benchmark measurements.

Retro terminal is the selected README hero, following the user’s choice. Its green and amber
pixel art depicts parallel evaluation tracks and organized outputs. All six options remain in the gallery.

## Validation and limits

- Ten documented command help paths passed through the actual Click CLI.
- Provider inventory returned the five providers documented in the README.
- All 64 local README/gallery links, image references, and heading fragments resolved.
- Markdown code fences are balanced; `git diff --check` passed.
- All six PNG headers and dimensions were checked; all six prompts are retained.

No live model evaluation, credentialed pipeline, release installation, or full application
suite was run for this documentation-only change. External URLs were not availability-checked.
Published release availability remains linked to the actual release pages rather than inferred
from source metadata. The wider documentation set was used as a reference, not comprehensively audited.
