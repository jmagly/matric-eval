# Research Gap Analysis - matric-eval

**Date**: 2026-01-24
**Project**: matric-eval
**Purpose**: Identify research papers needed to support LLM evaluation framework claims

## Executive Summary

matric-eval implements 8 benchmarks (HumanEval, MBPP, GSM8K, ARC, IFEval, DS-1000, LiveCodeBench, MT-Bench) plus tool calling evaluation. The current research-papers repo lacks foundational evaluation papers. This analysis identifies **10 high-priority papers** for acquisition.

## Current Coverage in research-papers

### Papers Already Available

| REF | Paper | Relevance to matric-eval |
|-----|-------|--------------------------|
| REF-014 | SWE-Bench | Real-world code evaluation methodology |
| REF-016 | Chain-of-Thought | Prompting for reasoning benchmarks |
| REF-017 | Self-Consistency | Multi-path evaluation strategy |
| REF-018 | ReAct | Tool calling patterns |
| REF-019 | Toolformer | Tool learning evaluation |

### Gap: Foundational Benchmark Papers (P1 - Critical)

| Priority | Paper | Year | Why Needed |
|----------|-------|------|------------|
| P1 | **HumanEval** (Chen et al.) | 2021 | Core benchmark - defines pass@k metric, 164 problems |
| P1 | **MBPP** (Austin et al.) | 2021 | Core benchmark - 974 Python problems |
| P1 | **GSM8K** (Cobbe et al.) | 2021 | Core benchmark - math reasoning |
| P1 | **MT-Bench** (Zheng et al.) | 2023 | Core benchmark - LLM-as-judge methodology |
| P1 | **ARC Challenge** (Clark et al.) | 2018 | Core benchmark - science reasoning |

### Gap: Advanced Evaluation Papers (P2 - Important)

| Priority | Paper | Year | Why Needed |
|----------|-------|------|------------|
| P2 | **IFEval** (Zhou et al.) | 2023 | Instruction following verification |
| P2 | **LiveCodeBench** (Jain et al.) | 2024 | Temporal contamination-resistant eval |
| P2 | **DS-1000** (Lai et al.) | 2022 | Data science evaluation methodology |
| P2 | **BigBench** (Srivastava et al.) | 2023 | Comprehensive capability testing |
| P2 | **HELM** (Liang et al.) | 2022 | Holistic evaluation framework |

### Gap: Foundational Theory Papers (P3 - Nice to Have)

| Priority | Paper | Year | Why Needed |
|----------|-------|------|------------|
| P3 | **Scaling Laws** (Kaplan et al.) | 2020 | Model size vs performance |
| P3 | **GPT-3** (Brown et al.) | 2020 | In-context learning foundation |
| P3 | **Chinchilla** (Hoffmann et al.) | 2022 | Compute-optimal training |
| P3 | **Llama** (Touvron et al.) | 2023 | Open model architecture |
| P3 | **RLHF** (Ouyang et al.) | 2022 | Alignment and fine-tuning |

## Acquisition Plan

### Phase 1: Core Benchmarks (Week 1)

**Target**: P1 papers - establish evaluation foundation

1. **HumanEval** (REF-034)
   - arXiv: 2107.03374
   - PDF: https://arxiv.org/pdf/2107.03374.pdf
   - Key sections: Pass@k definition (§4.1), problem format (§3)

2. **MBPP** (REF-035)
   - arXiv: 2108.07732
   - PDF: https://arxiv.org/pdf/2108.07732.pdf
   - Key sections: Dataset construction, function extraction

3. **GSM8K** (REF-036)
   - arXiv: 2110.14168
   - PDF: https://arxiv.org/pdf/2110.14168.pdf
   - Key sections: Problem format, verifier training

4. **MT-Bench** (REF-038)
   - arXiv: 2306.05685
   - PDF: https://arxiv.org/pdf/2306.05685.pdf
   - Key sections: LLM-as-judge methodology, multi-turn format

5. **ARC** (REF-041)
   - arXiv: 1803.05457
   - PDF: https://arxiv.org/pdf/1803.05457.pdf
   - Key sections: Easy/Challenge split, multiple choice format

### Phase 2: Advanced Benchmarks (Week 2)

**Target**: P2 papers - complete benchmark coverage

1. **IFEval** (REF-037)
   - arXiv: 2311.07911
   - PDF: https://arxiv.org/pdf/2311.07911.pdf
   - Key sections: Verifiable constraints, prompt categories

2. **LiveCodeBench** (REF-039)
   - arXiv: 2403.07974
   - PDF: https://arxiv.org/pdf/2403.07974.pdf
   - Key sections: Temporal splits, contamination prevention

3. **DS-1000** (REF-040)
   - arXiv: 2211.11501
   - PDF: https://arxiv.org/pdf/2211.11501.pdf
   - Key sections: Library coverage, execution evaluation

4. **HELM** (REF-042)
   - arXiv: 2211.09110
   - PDF: https://arxiv.org/pdf/2211.09110.pdf
   - Key sections: Taxonomy of capabilities, standardized evaluation

### Phase 3: Foundational (Week 3+)

**Target**: P3 papers - theoretical grounding

- Scaling Laws, GPT-3, Chinchilla, Llama, RLHF

## Documentation Standards

For each paper added to research-papers:

### File Structure
```
documentation/references/REF-XXX-{short-name}.md
pdfs/full/REF-XXX-{short-name}.pdf
bibliographies/master.bib (append BibTeX entry)
```

### Markdown Template
```markdown
# REF-XXX: {Paper Title}

## Metadata
- **Authors**: {names}
- **Year**: {year}
- **Venue**: {conference/journal}
- **arXiv**: {id}
- **PDF**: `pdfs/full/REF-XXX-*.pdf`

## Executive Summary
{2-3 sentence summary}

## Key Contributions
1. {contribution}
2. {contribution}
3. {contribution}

## Relevance to matric-eval
- {how this applies}
- {specific implementation notes}

## Key Quotes
> "{quote}" (p. {page})

## Implementation Notes
- {specific details for matric-eval}

## Cross-References
- Related: REF-XXX, REF-YYY
```

## Gitea Issue Creation

Create issues in research-papers repo for paper acquisition:

```bash
# Example issue template
Title: [PAPER] Add HumanEval benchmark paper (REF-034)

Description:
## Paper Details
- **Title**: Evaluating Large Language Models Trained on Code
- **Authors**: Chen et al.
- **Year**: 2021
- **arXiv**: 2107.03374

## Priority
P1 - Core benchmark for matric-eval

## Tasks
- [ ] Download PDF
- [ ] Create REF-034-humaneval-benchmark.md
- [ ] Add BibTeX entry
- [ ] Update INDEX.md

## Requester
matric-eval project
```

## Integration with matric-eval

After papers are added to research-papers:

1. Update `citable-claims-index.md` with verified REF numbers
2. Add inline citations to source code where applicable
3. Update benchmark documentation with methodology references
4. Cross-link in CLAUDE.md references section

## Metrics

| Metric | Current | Target |
|--------|---------|--------|
| P1 papers in repo | 0/5 | 5/5 |
| P2 papers in repo | 0/5 | 5/5 |
| P3 papers in repo | 0/5 | 3/5 |
| Claims with citations | ~30% | 90% |

## Timeline

| Week | Deliverable |
|------|-------------|
| 1 | P1 papers (HumanEval, MBPP, GSM8K, MT-Bench, ARC) |
| 2 | P2 papers (IFEval, LiveCodeBench, DS-1000, HELM) |
| 3+ | P3 papers as needed |

## References

- [research-papers repo](https://git.integrolabs.net/roctinam/research-papers)
- [ai-writing-guide research structure](https://git.integrolabs.net/roctinam/ai-writing-guide/.aiwg/research/)
- [matric-eval benchmarks](./../../src/matric_eval/tasks/)
