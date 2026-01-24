# matric-eval Session Initialization

Copy the prompt below to start a new Claude Code session in this directory.

---

## Initialization Prompt

```
I'm starting work on matric-eval, a consolidated model evaluation framework for the matric ecosystem.

**Context files to read first:**
- CLAUDE.md - Project context and MCP access
- PLANNING.md - Architecture decisions and requirements

**Background:**
We're consolidating evaluation code from matric-cli (TypeScript) and matric-memory (Rust) into a shared Python framework. The goal is to leverage existing eval frameworks (Inspect AI or lm-eval-harness) rather than building from scratch.

**Key requirements:**
1. Evaluate Ollama models against public benchmarks (HumanEval, MBPP, GSM8K, ARC, IFEval, etc.)
2. Run custom app-specific tests on top performers
3. Generate config recommendations (model → capability mapping)
4. **Critical: Robust recovery** - checkpoint/resume, selective re-run, gap detection

**Related repos (for reference):**
- /home/roctinam/dev/matric-cli - TypeScript eval code to migrate from
- /home/roctinam/dev/matric-memory - Rust eval code to migrate from
- /home/roctinam/data/evals - Public benchmark datasets

**First steps:**
1. Read CLAUDE.md and PLANNING.md
2. Prototype Inspect AI with Ollama - verify it works
3. Run one benchmark (HumanEval) against one model (llama3.2:3b)
4. Evaluate recovery/resume capabilities
5. If acceptable, scaffold the project structure

**Gitea issue:** roctinam/devops#5 has full project requirements

Start by reading the planning docs, then let's validate the framework choice with a quick prototype.
```

---

## Alternative: Shorter Version

```
Starting matric-eval - consolidated model evaluation framework.

Read CLAUDE.md and PLANNING.md first for full context.

Goal: Python framework using Inspect AI (or lm-eval-harness) for evaluating Ollama models. Must support checkpoint/resume and selective re-runs.

First task: Prototype Inspect AI + Ollama integration, run HumanEval against llama3.2:3b to validate the approach.

Related: /home/roctinam/dev/matric-cli/source/eval/ has current TypeScript implementation for reference.
```
