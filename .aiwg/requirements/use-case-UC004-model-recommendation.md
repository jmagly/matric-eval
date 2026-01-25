# Use Case UC004: Model Recommendation

**Document ID**: REQ-UC-004
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase
**Priority**: P1 - Critical

## Use Case Overview

| Attribute | Value |
|-----------|-------|
| Use Case ID | UC004 |
| Use Case Name | Model Recommendation |
| Created By | Claude Opus 4.5 |
| Created Date | 2026-01-24 |
| Last Updated | 2026-01-24 |
| Priority | P1 - Critical |
| Complexity | High |

## Traceability

**Traced to Gitea Issues**:
- #10: Generate model recommendations (model-categories.json)
- #18: Add configuration templates for matric apps

**Traced to Business Requirements**:
- BR-001: Unified Evaluation (consistent model selection across ecosystem)
- BR-002: Extensibility (support different application needs)
- BR-004: Developer Experience (automated config generation)

**Traced to Other Use Cases**:
- UC001: Run Benchmark Evaluation (provides data for recommendations)
- UC003: Custom Test Integration (custom tests influence recommendations)

## Actors

### Primary Actor

**Application Developer**: Developer integrating Ollama models into matric-cli, matric-memory, or other project.

**Role**: Needs curated list of recommended models for specific use cases.

**Characteristics**:
- May not be ML expert
- Wants quick answers: "Which model for code generation?"
- Values performance, quality, and resource efficiency
- Needs configuration that works out-of-the-box
- Updates models periodically (quarterly or when new releases available)

### Secondary Actors

**DevOps Engineer**: Manages deployment and resource allocation.

**Role**: Needs to understand resource requirements for recommended models.

**Characteristics**:
- Focuses on memory, GPU, inference latency
- Needs to plan infrastructure capacity
- Values predictable performance characteristics

**Product Manager**: Makes decisions about model quality vs. cost tradeoffs.

**Role**: Reviews recommendations and approves model upgrades.

### Supporting Actors

**matric-eval Framework**: Runs evaluation and generates recommendations.

**Ollama Service**: Provides available models and metadata.

**Configuration Management**: Consumes generated config files.

## Preconditions

### System State

1. **Ollama Running**: Service accessible with models available
2. **Evaluations Complete**: Full-tier evaluation finished for multiple models
3. **Results Available**: Evaluation results in standardized JSON format
4. **Baselines Defined**: Minimum acceptable scores for each capability
5. **Templates Available**: Config templates for matric-cli, matric-memory

### User State

1. **Requirements Known**: Developer knows which capabilities needed (code gen, reasoning, tool calling)
2. **Constraints Understood**: Resource limits (RAM, GPU, latency)
3. **Quality Expectations**: Minimum acceptable accuracy/performance

### Data State

1. **Multi-Model Results**: Evaluation results for 5+ models across all benchmarks
2. **Resource Metrics**: Model size, inference speed, memory usage captured
3. **Historical Data** (optional): Previous recommendations for comparison

## Postconditions

### Success Postconditions

1. **Config Generated**: `model-categories.json` created with recommendations
2. **Recommendations Justified**: Each recommendation includes reasoning and metrics
3. **Tiered Options**: Multiple tiers (fast/balanced/quality) for each capability
4. **Templates Updated**: Application-specific templates populated with recommended models
5. **Documentation Created**: README explaining how to use recommendations
6. **Validation Passed**: Generated config passes schema validation

### Failure Postconditions

1. **Error Logged**: Clear explanation of why recommendations couldn't be generated
2. **Partial Results**: If some categories fail, others still generated
3. **Fallback Config**: Default/previous config available if generation fails

## Main Success Scenario

### Scenario 1: Generate Recommendations for matric-cli

**Context**: Developer wants to update matric-cli with best models for code generation, reasoning, and tool calling.

**Steps**:

1. **Run Full Evaluation on Model Set**:
   ```bash
   # Evaluate 10 candidate models
   matric-eval --tier full --app matric-cli \
     --models llama3.2:1b,llama3.2:3b,codellama:7b,codellama:13b,mistral:7b,qwen2.5-coder:7b,deepseek-coder:6.7b,phi3:mini,gemma2:9b,llama3.1:8b \
     --output results/full-eval-20260124.json
   ```
   - Duration: 6-8 hours (parallel execution)
   - Output: Comprehensive results for all models across all benchmarks

2. **Invoke Recommendation Engine**:
   ```bash
   matric-eval --recommend \
     --input results/full-eval-20260124.json \
     --app matric-cli \
     --output model-categories.json \
     --verbose
   ```

3. **Analyze Results by Capability**:
   - Framework groups benchmarks by capability:
     - **Code Generation**: HumanEval, MBPP, DS-1000, LiveCodeBench, custom tool_calling
     - **Reasoning**: GSM8K, ARC
     - **Instruction Following**: IFEval
     - **General**: Average across all

4. **Rank Models per Capability**:
   - For each capability, rank models by composite score:
     ```
     Code Generation Rankings:
     1. codellama:13b - Score: 0.82, Size: 13GB, Speed: 15 tok/s
     2. qwen2.5-coder:7b - Score: 0.79, Size: 7GB, Speed: 28 tok/s
     3. deepseek-coder:6.7b - Score: 0.76, Size: 6.7GB, Speed: 25 tok/s
     4. codellama:7b - Score: 0.74, Size: 7GB, Speed: 22 tok/s
     5. llama3.2:3b - Score: 0.65, Size: 3GB, Speed: 45 tok/s
     ...
     ```

5. **Apply Filtering Criteria**:
   - **Minimum Quality**: Score >= 0.60 (configurable threshold)
   - **Resource Constraints**: Model size <= 20GB (default, configurable)
   - **Availability**: Model exists in Ollama registry
   - Remove models failing any criterion

6. **Create Tiered Recommendations**:
   - For each capability, select:
     - **Fast**: Smallest model meeting minimum quality (optimizes speed/memory)
     - **Balanced**: Best quality-to-resource ratio (Pareto optimal)
     - **Quality**: Highest scoring model regardless of size (within constraints)

   Example for Code Generation:
   ```
   Fast: llama3.2:3b (Score: 0.65, Size: 3GB, Speed: 45 tok/s)
   Balanced: qwen2.5-coder:7b (Score: 0.79, Size: 7GB, Speed: 28 tok/s)
   Quality: codellama:13b (Score: 0.82, Size: 13GB, Speed: 15 tok/s)
   ```

7. **Generate Configuration JSON**:
   ```json
   {
     "metadata": {
       "generated_at": "2026-01-24T15:30:00Z",
       "matric_eval_version": "0.2.0",
       "evaluation_id": "full-eval-20260124",
       "app": "matric-cli",
       "models_evaluated": 10,
       "benchmarks": ["humaneval", "mbpp", "gsm8k", "arc", "ifeval", "livecodebench", "ds1000", "tool_calling"],
       "total_samples": 3320
     },
     "capabilities": {
       "code_generation": {
         "description": "Generate Python/JavaScript code from natural language",
         "benchmarks": ["humaneval", "mbpp", "ds1000", "livecodebench", "tool_calling"],
         "recommendations": {
           "fast": {
             "model": "llama3.2:3b",
             "score": 0.65,
             "size_gb": 3,
             "inference_speed_tok_per_sec": 45,
             "memory_required_gb": 4,
             "latency_p95_ms": 1200,
             "justification": "Best performance for resource-constrained environments. Acceptable quality for simple code tasks.",
             "benchmark_scores": {
               "humaneval": 0.58,
               "mbpp": 0.62,
               "ds1000": 0.61,
               "livecodebench": 0.55,
               "tool_calling": 0.76
             },
             "use_cases": ["Quick code suggestions", "CLI autocomplete", "Simple scripts"]
           },
           "balanced": {
             "model": "qwen2.5-coder:7b",
             "score": 0.79,
             "size_gb": 7,
             "inference_speed_tok_per_sec": 28,
             "memory_required_gb": 8,
             "latency_p95_ms": 2100,
             "justification": "Excellent quality-to-resource ratio. Recommended for most production use cases.",
             "benchmark_scores": {
               "humaneval": 0.75,
               "mbpp": 0.78,
               "ds1000": 0.74,
               "livecodebench": 0.72,
               "tool_calling": 0.82
             },
             "use_cases": ["Production code generation", "Code review", "Documentation generation"]
           },
           "quality": {
             "model": "codellama:13b",
             "score": 0.82,
             "size_gb": 13,
             "inference_speed_tok_per_sec": 15,
             "latency_p95_ms": 3500,
             "justification": "Highest code generation quality. Use when accuracy critical.",
             "benchmark_scores": {
               "humaneval": 0.79,
               "mbpp": 0.81,
               "ds1000": 0.78,
               "livecodebench": 0.76,
               "tool_calling": 0.85
             },
             "use_cases": ["Critical code generation", "Complex algorithms", "Production-ready code"]
           }
         }
       },
       "reasoning": {
         "description": "Mathematical and logical reasoning",
         "benchmarks": ["gsm8k", "arc"],
         "recommendations": {
           "fast": {
             "model": "llama3.2:3b",
             "score": 0.62,
             "size_gb": 3,
             "justification": "Adequate reasoning for simple tasks.",
             "benchmark_scores": {
               "gsm8k": 0.61,
               "arc": 0.63
             }
           },
           "balanced": {
             "model": "llama3.1:8b",
             "score": 0.73,
             "size_gb": 8,
             "justification": "Strong reasoning capabilities with moderate resource usage.",
             "benchmark_scores": {
               "gsm8k": 0.72,
               "arc": 0.74
             }
           },
           "quality": {
             "model": "mistral:7b",
             "score": 0.76,
             "size_gb": 7,
             "justification": "Excellent reasoning, efficient size.",
             "benchmark_scores": {
               "gsm8k": 0.75,
               "arc": 0.77
             }
           }
         }
       },
       "instruction_following": {
         "description": "Follow complex instructions and constraints",
         "benchmarks": ["ifeval"],
         "recommendations": {
           "fast": {"model": "phi3:mini", "score": 0.68, "size_gb": 3.8},
           "balanced": {"model": "llama3.2:3b", "score": 0.71, "size_gb": 3},
           "quality": {"model": "llama3.1:8b", "score": 0.78, "size_gb": 8}
         }
       },
       "general": {
         "description": "General-purpose LLM tasks",
         "benchmarks": ["all"],
         "recommendations": {
           "fast": {
             "model": "llama3.2:3b",
             "score": 0.66,
             "justification": "Best all-around small model for matric-cli."
           },
           "balanced": {
             "model": "qwen2.5-coder:7b",
             "score": 0.77,
             "justification": "Recommended default for matric-cli. Strong code generation, good reasoning."
           },
           "quality": {
             "model": "codellama:13b",
             "score": 0.80,
             "justification": "Best overall quality for code-centric workloads."
           }
         }
       }
     },
     "default_model": "qwen2.5-coder:7b",
     "default_tier": "balanced",
     "minimum_requirements": {
       "ram_gb": 8,
       "disk_gb": 10,
       "recommended_gpu": "optional (CPU works, GPU 3x faster)"
     },
     "notes": [
       "Recommendations based on evaluation of 10 models across 3320 samples",
       "All models tested with Ollama 0.1.20 on Ubuntu 22.04",
       "Scores may vary based on hardware and Ollama version",
       "Update recommendations quarterly or when new models released"
     ]
   }
   ```

8. **Validate Configuration**:
   ```bash
   # Schema validation
   matric-eval --validate-config model-categories.json
   ```
   - Check: All required fields present
   - Check: Model names valid (exist in Ollama)
   - Check: Scores in valid range (0-1)
   - Check: Tiers properly ordered (fast < balanced < quality in size/score tradeoff)

9. **Update Application Templates**:
   - matric-cli config template (`templates/matric-cli-config.json`):
     ```json
     {
       "models": {
         "code_generation": "${CODE_GEN_MODEL:qwen2.5-coder:7b}",
         "reasoning": "${REASONING_MODEL:llama3.1:8b}",
         "default": "${DEFAULT_MODEL:qwen2.5-coder:7b}"
       },
       "inference": {
         "ollama_url": "http://localhost:11434",
         "timeout_ms": 30000,
         "max_retries": 3
       }
     }
     ```
   - Populate with "balanced" tier recommendations by default

10. **Generate Documentation**:
    - Create `MODEL_RECOMMENDATIONS.md`:
      ```markdown
      # Model Recommendations for matric-cli

      Generated: 2026-01-24
      Based on: Full evaluation of 10 models (3320 samples)

      ## Quick Start

      **Recommended default**: `qwen2.5-coder:7b`
      ```bash
      ollama pull qwen2.5-coder:7b
      matric-cli config set model qwen2.5-coder:7b
      ```

      ## By Use Case

      ### Code Generation
      - **Fast** (low resource): `llama3.2:3b` - Score: 65%, Size: 3GB
      - **Balanced** (recommended): `qwen2.5-coder:7b` - Score: 79%, Size: 7GB
      - **Quality** (best accuracy): `codellama:13b` - Score: 82%, Size: 13GB

      ### Reasoning
      - **Fast**: `llama3.2:3b` - Score: 62%
      - **Balanced**: `llama3.1:8b` - Score: 73%
      - **Quality**: `mistral:7b` - Score: 76%

      ## Performance Comparison

      | Model | Code | Reasoning | Speed | Size | Recommended For |
      |-------|------|-----------|-------|------|-----------------|
      | llama3.2:3b | 65% | 62% | 45 tok/s | 3GB | Resource-limited, quick tasks |
      | qwen2.5-coder:7b | 79% | 71% | 28 tok/s | 7GB | **Default - production use** |
      | codellama:13b | 82% | 68% | 15 tok/s | 13GB | Critical code generation |
      | llama3.1:8b | 72% | 73% | 22 tok/s | 8GB | Reasoning-heavy workloads |

      ## Detailed Benchmark Results

      [Link to full evaluation results](results/full-eval-20260124.json)

      ## How to Switch Models

      ```bash
      # Use fast tier (low resource)
      matric-cli config set model llama3.2:3b

      # Use quality tier (high accuracy)
      matric-cli config set model codellama:13b
      ```

      ## Update Schedule

      Re-run evaluation quarterly or when:
      - New Ollama models released
      - matric-cli requirements change
      - Performance issues reported

      ```bash
      # Re-generate recommendations
      matric-eval --tier full --app matric-cli --recommend
      ```
      ```

11. **Display Summary**:
    ```
    ✓ Recommendations generated: model-categories.json
    ✓ Template updated: templates/matric-cli-config.json
    ✓ Documentation created: MODEL_RECOMMENDATIONS.md

    Summary:
    - Models evaluated: 10
    - Benchmarks: 8 (3320 total samples)
    - Capabilities: 4 (code_generation, reasoning, instruction_following, general)
    - Recommended default: qwen2.5-coder:7b (balanced tier)

    Top recommendations:
    - Code Generation: qwen2.5-coder:7b (79% accuracy, 7GB)
    - Reasoning: llama3.1:8b (73% accuracy, 8GB)
    - Instruction Following: llama3.1:8b (78% accuracy, 8GB)

    Next steps:
    1. Review model-categories.json
    2. Pull recommended model: ollama pull qwen2.5-coder:7b
    3. Update matric-cli config: matric-cli config import model-categories.json
    ```

**Expected Duration**: 6-10 hours (mostly evaluation time), recommendation generation <5 minutes.

**Outcome**: Comprehensive, justified model recommendations with multi-tier options and clear documentation.

## Extensions and Alternate Flows

### Extension 1a: No Model Meets Minimum Quality Threshold

**Trigger**: Step 5 - All models score below minimum threshold for a capability.

**Steps**:
1. Log warning: "No models meet minimum quality threshold (0.60) for capability: reasoning"
2. Display scores:
   ```
   Reasoning scores (threshold: 0.60):
   - llama3.2:1b: 0.42
   - llama3.2:3b: 0.58
   - codellama:7b: 0.55
   ```
3. Prompt user:
   ```
   Options:
   1. Lower threshold to 0.50 (--min-score 0.50)
   2. Evaluate additional models
   3. Skip reasoning capability recommendations
   ```
4. If user lowers threshold, regenerate recommendations
5. If skipping, mark capability as "no recommendation" in config:
   ```json
   "reasoning": {
     "recommendations": null,
     "reason": "No models meet minimum quality threshold (0.60)",
     "best_available": {
       "model": "llama3.2:3b",
       "score": 0.58,
       "warning": "Below quality threshold, use with caution"
     }
   }
   ```

**Postcondition**: User aware of quality gap, can decide on threshold adjustment or additional evaluation.

### Extension 1b: Pareto Optimal Balanced Tier Ambiguous

**Trigger**: Step 6 - Multiple models with similar quality-to-resource ratio.

**Steps**:
1. Identify Pareto frontier (models not dominated by any other):
   ```
   Code Generation Pareto Optimal:
   - qwen2.5-coder:7b: Score 0.79, Size 7GB, Speed 28 tok/s
   - deepseek-coder:6.7b: Score 0.76, Size 6.7GB, Speed 25 tok/s
   - codellama:7b: Score 0.74, Size 7GB, Speed 22 tok/s
   ```
2. Apply tiebreaker criteria (configurable):
   - Prefer higher speed if score difference <3%
   - Prefer smaller size if speed difference <10%
   - Default: choose highest score
3. Document alternatives:
   ```json
   "balanced": {
     "model": "qwen2.5-coder:7b",
     "alternatives": [
       {
         "model": "deepseek-coder:6.7b",
         "score": 0.76,
         "note": "Slightly smaller, similar performance"
       }
     ]
   }
   ```

**Postcondition**: Clear primary recommendation with documented alternatives.

### Extension 2a: Resource Constraint Makes Quality Tier Unavailable

**Trigger**: Step 6 - Best model exceeds resource limits.

**Steps**:
1. Identify best model: `codellama:34b` (Score: 0.88, Size: 34GB)
2. Check against constraint: Max size 20GB
3. Log warning: "Best model (codellama:34b) exceeds size limit (34GB > 20GB)"
4. Fall back to best model within constraint:
   ```json
   "quality": {
     "model": "codellama:13b",
     "score": 0.82,
     "note": "Best model within 20GB size constraint. codellama:34b (0.88) available if constraint relaxed."
   }
   ```
5. Suggest constraint relaxation:
   ```
   To enable higher quality models, increase size limit:
   matric-eval --recommend --max-model-size 40GB
   ```

**Postcondition**: Quality tier uses best available within constraints, alternative documented.

### Extension 3a: Tie in Tier Selection (Same Score and Size)

**Trigger**: Step 6 - Two models identical in score and size.

**Steps**:
1. Apply secondary criteria:
   - Inference speed (prefer faster)
   - Community popularity (download count)
   - Recency (newer models preferred)
   - Alphabetical (last resort)
2. Document tie:
   ```json
   "fast": {
     "model": "llama3.2:3b",
     "note": "Selected over phi3:mini (same score/size) due to 10% faster inference"
   }
   ```

**Postcondition**: Deterministic selection with clear justification.

### Extension 4a: Custom Benchmark Weights

**Trigger**: Step 4 - User wants to weight certain benchmarks higher.

**Steps**:
1. Accept custom weights:
   ```bash
   matric-eval --recommend \
     --weights '{"humaneval": 2.0, "mbpp": 1.5, "gsm8k": 1.0, "tool_calling": 3.0}'
   ```
2. Calculate weighted scores:
   ```python
   weighted_score = (
       humaneval * 2.0 +
       mbpp * 1.5 +
       gsm8k * 1.0 +
       tool_calling * 3.0
   ) / (2.0 + 1.5 + 1.0 + 3.0)
   ```
3. Document weights in config:
   ```json
   "metadata": {
     "benchmark_weights": {
       "humaneval": 2.0,
       "mbpp": 1.5,
       "tool_calling": 3.0,
       "note": "Custom weights applied per matric-cli requirements"
     }
   }
   ```

**Postcondition**: Recommendations reflect application-specific priorities.

### Extension 5a: Historical Comparison

**Trigger**: Step 11 - User wants to compare new recommendations with previous.

**Steps**:
1. Load previous recommendations:
   ```bash
   matric-eval --recommend --compare model-categories-20251024.json
   ```
2. Generate diff:
   ```
   Model Recommendation Changes:

   Code Generation (Balanced):
     Previous: codellama:7b (Score: 0.74, Size: 7GB)
     Current:  qwen2.5-coder:7b (Score: 0.79, Size: 7GB)
     Change:   +6.8% accuracy, same size

   Reasoning (Quality):
     Previous: mistral:7b (Score: 0.76)
     Current:  mistral:7b (Score: 0.76)
     Change:   No change

   Default Model:
     Previous: codellama:7b
     Current:  qwen2.5-coder:7b
     Reason:   Superior code generation, same resource usage
   ```
3. Include in documentation:
   ```markdown
   ## Changes from Previous Recommendations

   - **Code Generation (Balanced)**: Upgraded to qwen2.5-coder:7b (+6.8% accuracy)
   - **Reasoning**: No change (mistral:7b still optimal)
   - **Default**: qwen2.5-coder:7b (replaces codellama:7b)
   ```

**Postcondition**: Clear understanding of recommendation evolution.

### Extension 6a: Application-Specific Constraints

**Trigger**: Step 6 - matric-memory has different constraints than matric-cli.

**Steps**:
1. Load application profile:
   ```python
   APP_PROFILES = {
       "matric-cli": {
           "primary_capability": "code_generation",
           "max_latency_ms": 5000,
           "max_size_gb": 20,
           "preferred_speed": "high"
       },
       "matric-memory": {
           "primary_capability": "reasoning",
           "max_latency_ms": 10000,
           "max_size_gb": 30,
           "preferred_quality": "high"
       }
   }
   ```
2. Apply profile filters:
   - matric-cli: Prioritize speed, limit size to 20GB
   - matric-memory: Prioritize quality, allow up to 30GB
3. Generate app-specific recommendations:
   ```json
   {
     "app": "matric-memory",
     "profile": {
       "primary_capability": "reasoning",
       "constraints": {
         "max_latency_ms": 10000,
         "max_size_gb": 30
       }
     },
     "capabilities": {
       "reasoning": {
         "quality": {
           "model": "llama3.1:70b",
           "score": 0.85,
           "note": "Uses full 30GB allowance for best reasoning quality"
         }
       }
     }
   }
   ```

**Postcondition**: Each application gets tailored recommendations matching its needs.

### Extension 7a: Model Unavailable in Ollama Registry

**Trigger**: Step 8 - Validation finds recommended model not in registry.

**Steps**:
1. Query Ollama registry:
   ```bash
   ollama list --remote | grep qwen2.5-coder:7b
   ```
2. If not found, log error:
   ```
   ERROR: Recommended model 'qwen2.5-coder:7b' not available in Ollama registry.

   This may indicate:
   - Model name typo
   - Model not yet released
   - Ollama version too old

   Falling back to next best: deepseek-coder:6.7b
   ```
3. Update recommendation with fallback
4. Document issue:
   ```json
   "balanced": {
     "model": "deepseek-coder:6.7b",
     "note": "Originally qwen2.5-coder:7b, but unavailable in registry. This is fallback."
   }
   ```

**Postcondition**: Recommendations only include available models.

### Extension 8a: Export to Other Formats

**Trigger**: Step 9 - User needs YAML, TOML, or language-specific config.

**Steps**:
1. Generate multiple formats:
   ```bash
   matric-eval --recommend --format json,yaml,toml,typescript
   ```
2. Create format-specific files:
   - `model-categories.json` (default)
   - `model-categories.yaml`
   - `model-categories.toml`
   - `model-categories.ts` (TypeScript type definitions)
3. TypeScript example:
   ```typescript
   // model-categories.ts
   export interface ModelRecommendation {
     model: string;
     score: number;
     size_gb: number;
     justification: string;
   }

   export const MODEL_CATEGORIES = {
     code_generation: {
       fast: { model: "llama3.2:3b", score: 0.65, size_gb: 3 },
       balanced: { model: "qwen2.5-coder:7b", score: 0.79, size_gb: 7 },
       quality: { model: "codellama:13b", score: 0.82, size_gb: 13 }
     }
   } as const;
   ```

**Postcondition**: Config available in formats suitable for different applications.

### Extension 9a: Continuous Recommendation Updates

**Trigger**: User wants automated quarterly updates.

**Steps**:
1. Set up scheduled evaluation:
   ```yaml
   # .github/workflows/model-eval-quarterly.yml
   on:
     schedule:
       - cron: '0 0 1 */3 *'  # Every 3 months
   jobs:
     evaluate-and-recommend:
       runs-on: ubuntu-latest
       steps:
         - name: Run Evaluation
           run: matric-eval --tier full --app matric-cli
         - name: Generate Recommendations
           run: matric-eval --recommend --output new-recommendations.json
         - name: Compare with Current
           run: matric-eval --recommend --compare model-categories.json
         - name: Create PR
           run: gh pr create --title "Model Recommendations Update Q${QUARTER}"
   ```
2. Automated PR includes:
   - Updated `model-categories.json`
   - Comparison with previous recommendations
   - Full evaluation results
3. Team reviews and approves

**Postcondition**: Recommendations stay current with minimal manual effort.

## Special Requirements

### Performance Requirements

- **Recommendation Generation**: <5 minutes for 10 models
- **Config Validation**: <1 second
- **Template Population**: <1 second

### Reliability Requirements

- **Deterministic**: Same evaluation data produces same recommendations
- **Graceful Degradation**: Missing benchmarks reduce confidence but don't block recommendations
- **Validation**: All recommendations validated before output

### Usability Requirements

- **Clear Justifications**: Every recommendation includes "why" explanation
- **Tiered Options**: User can choose fast/balanced/quality based on needs
- **Documentation**: Auto-generated docs explain how to use recommendations
- **Comparison**: Easy to compare with previous recommendations

## Assumptions and Dependencies

### Assumptions

1. **Evaluation Completeness**: Full-tier evaluation covers all relevant benchmarks
2. **Representative Benchmarks**: Public benchmarks correlate with real-world performance
3. **Static Models**: Model weights don't change between evaluation and deployment
4. **Ollama Compatibility**: All recommended models work with target Ollama version

### Dependencies

- **Evaluation Results**: Complete, valid JSON from full-tier evaluation
- **Ollama Registry**: Ability to query available models
- **Config Templates**: Application-specific templates for population
- **Validation Schema**: JSON schema for config validation

## Validation Criteria

### Acceptance Criteria

- [ ] `model-categories.json` generated with all required fields
- [ ] Recommendations include fast/balanced/quality tiers for each capability
- [ ] Every recommendation includes justification and benchmark scores
- [ ] Default model selected and documented
- [ ] Generated config passes schema validation
- [ ] Recommended models available in Ollama registry
- [ ] Documentation auto-generated and human-readable
- [ ] Application templates updated with balanced-tier recommendations
- [ ] Comparison with previous recommendations works (if available)
- [ ] Export to YAML, TOML, TypeScript formats supported

### Non-Acceptance Criteria

- [ ] Recommendations without justification
- [ ] Tiers improperly ordered (fast tier larger than quality tier)
- [ ] Recommended model not available in Ollama
- [ ] Invalid JSON schema
- [ ] No documentation generated
- [ ] Missing capabilities from evaluation results

## Notes

### Recommendation Algorithm

```python
def generate_recommendations(eval_results, app_profile):
    capabilities = group_benchmarks_by_capability(eval_results)

    recommendations = {}
    for capability, benchmarks in capabilities.items():
        # Calculate composite scores
        model_scores = calculate_composite_scores(benchmarks)

        # Apply filters
        filtered = apply_filters(
            model_scores,
            min_score=app_profile.min_score,
            max_size=app_profile.max_size,
            max_latency=app_profile.max_latency
        )

        # Select tiers
        recommendations[capability] = {
            "fast": select_fast_tier(filtered),      # Min size
            "balanced": select_balanced_tier(filtered),  # Pareto optimal
            "quality": select_quality_tier(filtered)     # Max score
        }

    return recommendations
```

### Tier Selection Criteria

- **Fast**: Minimize `size_gb` subject to `score >= min_score`
- **Balanced**: Maximize `score / size_gb` (Pareto optimal point)
- **Quality**: Maximize `score` subject to `size_gb <= max_size`

### Testing Strategy

1. **Unit Tests**: Test recommendation algorithm with synthetic data
2. **Integration Tests**: Run full evaluation + recommendation pipeline
3. **Validation Tests**: Verify config schema and model availability
4. **Regression Tests**: Compare recommendations with known baselines
5. **Documentation Tests**: Verify generated docs are valid Markdown

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial model recommendation use case |
