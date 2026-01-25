/**
 * @matric/eval-client
 *
 * TypeScript client for the matric-eval evaluation framework.
 *
 * @example
 * ```typescript
 * import { createClient, type EvalOptions } from '@matric/eval-client';
 *
 * const client = createClient();
 *
 * // Run a quick evaluation
 * const summary = await client.run({
 *   tier: 'quick',
 *   models: ['llama3.2:3b', 'qwen2.5:7b'],
 * });
 *
 * console.log(`Evaluated ${summary.successful} models`);
 *
 * // Generate recommendations
 * const report = await client.recommend({
 *   input: summary.outputDir,
 * });
 *
 * console.log(`Best overall: ${report.bestOverall}`);
 *
 * // Export for matric-cli
 * await client.exportModelCategories(report, '.aiwg/config/model-categories.json');
 * ```
 *
 * @packageDocumentation
 */

// Client exports
export { MatricEvalClient, MatricEvalError, createClient } from './client.js';

// Type exports
export type {
  BenchmarkId,
  BenchmarkResult,
  CapabilityCategory,
  CapabilityScore,
  EvalOptions,
  EvalSummary,
  EvalTier,
  LogLevel,
  ModelCategoriesConfig,
  ModelRecommendation,
  ModelResult,
  OutputFormat,
  RecommendOptions,
  RecommendationReport,
} from './types.js';
