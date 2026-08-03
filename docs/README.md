# matric-eval Documentation

Comprehensive documentation for the matric-eval model evaluation framework.

## Quick Links

- [Architecture Overview](architecture/overview.md) - System design and component structure
- [Roadmap](development/roadmap.md) - Current support, release gates, and live milestones
- [Delivery Plan](development/planning.md) - Ordered 0.2.0 work and acceptance gates
- [Traceability Matrix](requirements/traceability-matrix.md) - Living requirement-to-evidence mapping
- [Operational Validation](validation/operational-validation-v1.md) - Pinned scorer and reliability evidence
- [Testing Guide](testing/contributing.md) - How to run and write tests

## Documentation Structure

### Architecture

Technical design documentation and architectural decisions.

- [**Overview (SAD)**](architecture/overview.md) - Software Architecture Document
- **Decisions (ADRs)**
  - [ADR-001: Python Core with Bindings](architecture/decisions/ADR-001-python-core-with-bindings.md)
  - [ADR-002: Inspect AI Framework](architecture/decisions/ADR-002-inspect-ai-framework.md)
  - [ADR-003: JSONL Test Format](architecture/decisions/ADR-003-jsonl-test-format.md)
  - [ADR-004: Tiered Evaluation](architecture/decisions/ADR-004-tiered-evaluation.md)
  - [ADR-005: Checkpoint/Resume Design](architecture/decisions/ADR-005-checkpoint-resume-design.md)

### Requirements

Current traceability plus the archived v0.1 requirements baseline.

- [**Vision**](requirements/vision.md) - Archived v0.1 project vision and business case
- [**Supplementary Requirements**](requirements/supplementary-requirements.md) - Archived v0.1 non-functional requirements baseline
- [**Traceability Matrix**](requirements/traceability-matrix.md) - Requirements to implementation mapping
- **Use Cases**
  - [UC001: Run Benchmark](requirements/use-cases/use-case-UC001-run-benchmark.md)
  - [UC002: Checkpoint/Resume](requirements/use-cases/use-case-UC002-checkpoint-resume.md)
  - [UC003: Custom Tests](requirements/use-cases/use-case-UC003-custom-tests.md)
  - [UC004: Model Recommendation](requirements/use-cases/use-case-UC004-model-recommendation.md)
  - [UC005: CI/CD Integration](requirements/use-cases/use-case-UC005-cicd-integration.md)

### Testing

Test strategy, plans, and contribution guidelines.

- [**Strategy**](testing/strategy.md) - Overall testing approach
- [**Contributing**](testing/contributing.md) - How to write and run tests
- **Test Plans**
  - [Unit Tests](testing/plans/unit.md)
  - [Integration Tests](testing/plans/integration.md)

### Deployment

CI/CD and release documentation.

- [**CI/CD Pipeline**](deployment/cicd-pipeline.md) - Gitea Actions workflow
- [**Release Notes Template**](deployment/release-notes-template.md) - Release documentation format
- [**0.2.0 Release Notes**](releases/0.2.0.md) - Compatibility, installation, limits, and evidence

### Development

Planning and implementation guides.

- [**Planning**](development/planning.md) - Current 0.2.0 delivery sequence and gates
- [**Roadmap**](development/roadmap.md) - Supported capabilities and live milestones
- [**Checkpoint/Resume**](development/checkpoint-resume.md) - Implementation details for fault tolerance
- [**Session Init**](development/session-init.md) - Development session initialization

### Research

Background research and academic references.

- [**Citable Claims Index**](research/citable-claims-index.md) - Referenced research papers
- [**Research Gap Analysis**](research/research-gap-analysis.md) - Areas for improvement
- [**Self-Evaluation Research**](research/self-evaluation-research-based.md) - LLM self-evaluation approaches

### Benchmark Protocols

- [**Reproducibility and Freshness**](benchmarks/reproducibility.md) - Version and source policy
- [**Wave 1 Protocols**](benchmarks/wave1-protocols.md) - Initial expansion decisions
- [**Wave 2 Protocols**](benchmarks/wave2-protocols.md) - Successor and security benchmarks
- [**Wave 3 Protocols**](benchmarks/wave3-protocols.md) - Long-context and memory benchmarks

## Getting Started

1. Check the [Roadmap](development/roadmap.md) for current support and release status
2. Review the [Architecture Overview](architecture/overview.md) for system design
3. Use the [Traceability Matrix](requirements/traceability-matrix.md) for current evidence
4. See [Testing Guide](testing/contributing.md) for development workflow
