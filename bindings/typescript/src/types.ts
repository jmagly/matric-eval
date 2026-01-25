/**
 * Type definitions for matric-eval TypeScript bindings.
 *
 * These types are compatible with matric-cli's model category system.
 */

/**
 * Evaluation tier - controls sample size and benchmark depth.
 */
export type EvalTier = 'smoke' | 'quick' | 'full';

/**
 * Output format for evaluation results.
 */
export type OutputFormat = 'json' | 'table' | 'summary';

/**
 * Log level for evaluation runs.
 */
export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';

/**
 * Capability category for model recommendations.
 */
export type CapabilityCategory =
  | 'code_generation'
  | 'math_reasoning'
  | 'instruction_following'
  | 'reasoning'
  | 'conversation'
  | 'tool_use';

/**
 * Benchmark identifiers.
 */
export type BenchmarkId =
  | 'humaneval'
  | 'mbpp'
  | 'gsm8k'
  | 'arc'
  | 'ifeval'
  | 'ds1000'
  | 'livecodebench'
  | 'mtbench'
  | 'tool_calling';

/**
 * Benchmark result for a single benchmark.
 */
export interface BenchmarkResult {
  /** Benchmark identifier */
  benchmark: BenchmarkId;
  /** Number of samples evaluated */
  samples: number;
  /** Score (0.0 to 1.0) */
  score: number;
  /** Accuracy percentage (0-100) */
  accuracy?: number;
  /** Pass rate for code benchmarks */
  passRate?: number;
  /** Evaluation duration in seconds */
  duration?: number;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Result for a single model evaluation.
 */
export interface ModelResult {
  /** Model identifier (e.g., "llama3.2:3b") */
  model: string;
  /** Evaluation tier used */
  tier: EvalTier;
  /** Status of the evaluation */
  status: 'success' | 'failed' | 'skipped';
  /** Overall weighted score (0.0 to 1.0) */
  overallScore: number;
  /** Model size in GB */
  sizeGb: number;
  /** Results by benchmark */
  benchmarks: Record<BenchmarkId, BenchmarkResult>;
  /** Error message if failed */
  error?: string;
  /** Evaluation timestamp */
  timestamp: string;
}

/**
 * Capability score for a model.
 */
export interface CapabilityScore {
  /** Capability category */
  capability: CapabilityCategory;
  /** Score (0.0 to 1.0) */
  score: number;
  /** Contributing benchmarks */
  benchmarks: BenchmarkId[];
}

/**
 * Model recommendation for a capability.
 */
export interface ModelRecommendation {
  /** Capability this recommendation is for */
  capability: CapabilityCategory;
  /** Recommended model */
  recommended: string;
  /** Recommendation score */
  score: number;
  /** Alternative models */
  alternatives: Array<{ model: string; score: number }>;
  /** Reasoning for recommendation */
  rationale: string;
}

/**
 * Complete recommendation report.
 */
export interface RecommendationReport {
  /** Recommendations by capability */
  recommendations: Record<CapabilityCategory, ModelRecommendation>;
  /** Scores for all evaluated models */
  modelScores: Record<string, {
    model: string;
    benchmarkScores: Record<string, number>;
    capabilityScores: Record<string, number>;
    overallScore: number;
    sizeGb: number;
  }>;
  /** Best overall model */
  bestOverall: string;
  /** Best balanced model (good across all capabilities) */
  bestBalanced: string;
  /** Report metadata */
  metadata: Record<string, unknown>;
}

/**
 * Model categories format compatible with matric-cli.
 *
 * This format can be written to model-categories.json for use
 * with matric-cli's model selection system.
 */
export interface ModelCategoriesConfig {
  /** Configuration version */
  version: string;
  /** Generator identifier */
  generatedBy: 'matric-eval';
  /** Best overall model */
  bestOverall: string;
  /** Category configurations */
  categories: Record<string, {
    description: string;
    recommended: string;
    alternatives: string[];
    score: number;
  }>;
}

/**
 * Options for running an evaluation.
 */
export interface EvalOptions {
  /** Evaluation tier (default: 'smoke') */
  tier?: EvalTier;
  /** Specific models to evaluate (default: all available) */
  models?: string[];
  /** Specific benchmarks to run (default: all for tier) */
  benchmarks?: BenchmarkId[];
  /** Output directory for results */
  outputDir?: string;
  /** Maximum model size in GB to evaluate */
  maxModelSizeGb?: number;
  /** Timeout per sample in seconds */
  timeout?: number;
  /** Number of parallel evaluations */
  parallelism?: number;
  /** Resume from checkpoint */
  resume?: boolean;
  /** Log level */
  logLevel?: LogLevel;
  /** Path to matric-eval executable (default: 'matric-eval') */
  executablePath?: string;
}

/**
 * Options for generating recommendations.
 */
export interface RecommendOptions {
  /** Path to results directory or summary.json */
  input: string;
  /** Output path for recommendations */
  output?: string;
  /** Minimum score threshold (default: 0.3) */
  minScore?: number;
  /** Path to matric-eval executable */
  executablePath?: string;
}

/**
 * Evaluation summary returned after a run.
 */
export interface EvalSummary {
  /** Total models evaluated */
  totalModels: number;
  /** Successful evaluations */
  successful: number;
  /** Failed evaluations */
  failed: number;
  /** Skipped models */
  skipped: number;
  /** Total duration in seconds */
  durationSeconds: number;
  /** Results for each model */
  results: ModelResult[];
  /** Output directory path */
  outputDir: string;
}
