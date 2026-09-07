/**
 * TypeScript client for matric-eval evaluation framework.
 *
 * Provides a programmatic interface to invoke the matric-eval CLI
 * and parse results for use in TypeScript/JavaScript applications.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { readConsumerResult, projectLegacy, readRecommendationReport, type RecommendationReportV2, type ConsumerResult, type VersionedEvaluation } from './consumer-results.js';

import type {
  BenchmarkId,
  ExecutionOptions,
  EvalOptions,
  EvalSummary,
  EvalTier,
  ModelCategoriesConfig,
  ModelResult,
  RecommendOptions,
  RecommendationReport,
} from './types.js';

/**
 * Error thrown when matric-eval execution fails.
 */
export class MatricEvalError extends Error {
  constructor(
    message: string,
    public readonly exitCode: number | null,
    public readonly stderr: string,
    public readonly cancelled = false,
  ) {
    super(message);
    this.name = 'MatricEvalError';
  }
}

/**
 * Result of executing a command.
 */
interface CommandResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

/**
 * Client for interacting with matric-eval.
 *
 * @example
 * ```typescript
 * import { MatricEvalClient } from '@matric/eval-client';
 *
 * const client = new MatricEvalClient();
 *
 * // Run evaluation
 * const summary = await client.run({
 *   tier: 'quick',
 *   models: ['llama3.2:3b'],
 * });
 *
 * // Generate recommendations
 * const report = await client.recommend({
 *   input: summary.outputDir,
 * });
 *
 * // Reports without an explicit capability policy retain exclusions.
 * console.log(report.status);
 * ```
 */
export class MatricEvalClient {
  private readonly executablePath: string;

  /**
   * Create a new matric-eval client.
   *
   * @param executablePath - Path to matric-eval executable (default: 'matric-eval')
   */
  constructor(executablePath = 'matric-eval') {
    this.executablePath = executablePath;
  }

  /**
   * Execute a command and return the result.
   */
  private async execute(
    args: string[],
    execution: ExecutionOptions = {},
    executablePath = this.executablePath,
  ): Promise<CommandResult> {
    return new Promise((resolve, reject) => {
      if (execution.signal?.aborted) {
        reject(new MatricEvalError('matric-eval execution cancelled', null, '', true));
        return;
      }
      const proc: ChildProcess = spawn(executablePath, args, {
        stdio: ['inherit', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';
      let settled = false;
      let cancelled = false;

      const abort = () => {
        cancelled = true;
        proc.kill('SIGTERM');
      };
      const cleanup = () => execution.signal?.removeEventListener('abort', abort);
      execution.signal?.addEventListener('abort', abort, { once: true });

      proc.stdout?.on('data', (data: Buffer) => {
        const chunk = data.toString();
        stdout += chunk;
        execution.onStdout?.(chunk);
      });

      proc.stderr?.on('data', (data: Buffer) => {
        const chunk = data.toString();
        stderr += chunk;
        execution.onStderr?.(chunk);
      });

      proc.on('error', (error) => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(new MatricEvalError(`Failed to execute matric-eval: ${error.message}`, null, ''));
      });

      proc.on('close', (code) => {
        if (settled) return;
        settled = true;
        cleanup();
        if (cancelled) {
          reject(new MatricEvalError('matric-eval execution cancelled', code, stderr, true));
          return;
        }
        resolve({
          stdout,
          stderr,
          exitCode: code ?? 0,
        });
      });
    });
  }

  /**
   * Check if matric-eval is available.
   *
   * @returns true if matric-eval is installed and accessible
   */
  async isAvailable(execution: ExecutionOptions = {}): Promise<boolean> {
    try {
      const result = await this.execute(['--version'], execution);
      return result.exitCode === 0;
    } catch {
      return false;
    }
  }

  /**
   * Get the version of matric-eval.
   *
   * @returns Version string
   */
  async getVersion(execution: ExecutionOptions = {}): Promise<string> {
    const result = await this.execute(['--version'], execution);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Failed to get version', result.exitCode, result.stderr);
    }
    return result.stdout.trim();
  }

  /**
   * List available models.
   *
   * @returns Array of model names
   */
  async listModels(execution: ExecutionOptions = {}): Promise<string[]> {
    const result = await this.execute(
      ['list-models', '--output-format', 'json'],
      execution,
    );
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Failed to list models', result.exitCode, result.stderr);
    }

    const data = JSON.parse(result.stdout) as
      | Array<{ name: string }>
      | { models: Array<{ name: string }> };
    const models = Array.isArray(data) ? data : data.models;
    return models.map((model) => model.name);
  }

  /**
   * List available benchmarks.
   *
   * @param tier - Optional tier to filter benchmarks
   * @returns Array of benchmark identifiers
   */
  async listBenchmarks(
    tier?: EvalTier,
    execution: ExecutionOptions = {},
  ): Promise<BenchmarkId[]> {
    const args = ['list-benchmarks', '--output-format', 'json'];
    if (tier) {
      args.push('--tier', tier);
    }

    const result = await this.execute(args, execution);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Failed to list benchmarks', result.exitCode, result.stderr);
    }

    const data = JSON.parse(result.stdout) as
      | Record<string, unknown>
      | { benchmarks: Array<{ name: string }> };
    if ('benchmarks' in data && Array.isArray(data.benchmarks)) {
      return data.benchmarks.map((benchmark) => benchmark.name as BenchmarkId);
    }
    return Object.keys(data) as BenchmarkId[];
  }

  /**
   * Run an evaluation.
   *
   * @param options - Evaluation options
   * @returns Evaluation summary
   */
  async run(options: EvalOptions & { resultFormat: 'v2' }, execution?: ExecutionOptions): Promise<VersionedEvaluation>;
  async run(options?: EvalOptions & { resultFormat?: 'legacy' }, execution?: ExecutionOptions): Promise<EvalSummary>;
  async run(options: EvalOptions, execution?: ExecutionOptions): Promise<EvalSummary | VersionedEvaluation>;
  async run(
    options: EvalOptions = {},
    execution: ExecutionOptions = {},
  ): Promise<EvalSummary | VersionedEvaluation> {
    if ((options.models?.length ?? 0) > 1) {
      throw new MatricEvalError('The matric-eval 0.2 CLI accepts one explicit model', null, '');
    }
    if (options.timeout !== undefined || options.parallelism !== undefined) {
      throw new MatricEvalError(
        'timeout and parallelism are not supported by the matric-eval 0.2 CLI',
        null,
        '',
      );
    }
    if (options.resume === true) {
      throw new MatricEvalError('resume requires a checkpoint run ID or path', null, '');
    }

    const args: string[] = [];
    if (options.logLevel) {
      args.push('--log-level', options.logLevel.toLowerCase());
    }
    args.push('run', '--output-format', 'json');
    if (options.resultFormat) args.push('--result-format', options.resultFormat);

    if (options.tier) {
      args.push('--tier', options.tier);
    }

    if (options.models?.[0]) {
      args.push('--model', options.models[0]);
    }

    if (options.benchmarks && options.benchmarks.length > 0) {
      for (const benchmark of options.benchmarks) {
        args.push('--benchmark', benchmark);
      }
    }

    if (options.outputDir) {
      args.push('--output', options.outputDir);
    }

    if (options.maxModelSizeGb !== undefined) {
      args.push('--max-size', options.maxModelSizeGb.toString());
    }

    if (typeof options.resume === 'string') {
      args.push('--resume', options.resume);
    }

    if (options.provider) {
      args.push('--provider', options.provider);
    }

    if (options.providerUrl) {
      args.push('--provider-url', options.providerUrl);
    }

    if (options.apiKey) {
      args.push('--api-key', options.apiKey);
    }

    if (options.thinking) {
      args.push('--thinking', options.thinking);
    }

    if (options.judge) {
      args.push('--judge', options.judge);
    }

    const result = await this.execute(args, execution, options.executablePath);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Evaluation failed', result.exitCode, result.stderr);
    }

    if (options.resultFormat === 'v2') {
      const parsed = readConsumerResult(result.stdout);
      if (!('result_schema_version' in parsed) && !('result_collection_schema_version' in parsed)) throw new MatricEvalError('Expected versioned evaluation result', null, '');
      return parsed;
    }
    return this.parseEvalSummary(result.stdout);
  }

  async evaluate(options: EvalOptions & { resultFormat: 'v2' }, execution?: ExecutionOptions): Promise<VersionedEvaluation>;
  async evaluate(options?: EvalOptions & { resultFormat?: 'legacy' }, execution?: ExecutionOptions): Promise<EvalSummary>;
  async evaluate(options: EvalOptions, execution?: ExecutionOptions): Promise<EvalSummary | VersionedEvaluation>;
  async evaluate(options: EvalOptions = {}, execution: ExecutionOptions = {}): Promise<EvalSummary | VersionedEvaluation> {
    return options.resultFormat === 'v2' ? this.run({...options, resultFormat: 'v2'}, execution) : this.run({...options, resultFormat: 'legacy'}, execution);
  }

  async loadResult(sourcePath: string): Promise<ConsumerResult> {
    const bytes = await fs.readFile(sourcePath);
    return readConsumerResult(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
  }

  /**
   * Generate recommendations from evaluation results.
   *
   * @param options - Recommendation options
   * @returns Recommendation report
   */
  async recommend(
    options: RecommendOptions,
    execution: ExecutionOptions = {},
  ): Promise<RecommendationReportV2> {
    const args = ['recommend', '--results-dir', options.input, '--output-format', 'json'];

    if (options.capabilityPolicy) args.push('--capability-policy', options.capabilityPolicy);
    if (options.minScore !== undefined) {
      args.push('--min-score', options.minScore.toString());
    }

    const result = await this.execute(args, execution, options.executablePath);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Failed to generate recommendations', result.exitCode, result.stderr);
    }

    const report = readRecommendationReport(result.stdout);
    if (options.output) {
      const outputDir = path.dirname(options.output);
      await fs.mkdir(outputDir, { recursive: true });
      await fs.writeFile(options.output, JSON.stringify(report, null, 2));
    }
    return report;
  }

  /**
   * Export recommendations as model-categories.json format.
   *
   * This format is compatible with matric-cli's model selection system.
   *
   * @param report - Recommendation report
   * @param outputPath - Output file path
   */
  async exportModelCategories(
    report: RecommendationReport | RecommendationReportV2,
    outputPath: string,
  ): Promise<void> {
    if ('recommendation_schema_version' in report) throw new MatricEvalError('legacy_projection_unrepresentable:model_categories', null, '');
    const config: ModelCategoriesConfig = {
      version: '1.0',
      generatedBy: 'matric-eval',
      bestOverall: report.bestOverall,
      categories: {},
    };

    for (const [capability, rec] of Object.entries(report.recommendations)) {
      config.categories[capability] = {
        description: rec.rationale,
        recommended: rec.recommended,
        alternatives: rec.alternatives.slice(0, 2).map((a) => a.model),
        score: rec.score,
      };
    }

    const outputDir = path.dirname(outputPath);
    await fs.mkdir(outputDir, { recursive: true });
    await fs.writeFile(outputPath, JSON.stringify(config, null, 2));
  }

  /**
   * Load evaluation results from a summary.json file.
   *
   * @param summaryPath - Path to summary.json
   * @returns Evaluation summary
   */
  async loadSummary(summaryPath: string): Promise<EvalSummary> {
    const content = await fs.readFile(summaryPath, 'utf-8');
    return this.parseEvalSummary(content);
  }

  /**
   * Parse evaluation summary from JSON string.
   */
  private parseEvalSummary(json: string): EvalSummary {
    const data = projectLegacy(readConsumerResult(json));
    const rawResults = Array.isArray(data['results'])
      ? data['results']
      : 'model' in data
        ? [data]
        : [];
    const results: ModelResult[] = rawResults.map((r) => {
      const result = r as Record<string, unknown>;
      if (Object.hasOwn(result, 'result_schema_version')) {
        throw new Error('Versioned results require the validated readResult v2 reader');
      }
      if (result['overall_score'] === null) {
        throw new Error('Unavailable overall scores cannot be projected into the legacy numeric contract');
      }
      const rawStatus = String(result['status'] ?? 'failed');
      const status = rawStatus === 'error' ? 'failed' : rawStatus;
      return {
        qualification: 'legacy_unverified',
        model: String(result['model']),
        tier: (result['tier'] as EvalTier) ?? 'smoke',
        status: status as 'success' | 'failed' | 'skipped',
        overallScore: result['overall_score'] as number,
        sizeGb: typeof result['size_gb'] === 'number' ? result['size_gb'] : null,
        benchmarks: (result['benchmarks'] as Record<BenchmarkId, unknown>) ?? {},
        error: result['error'] as string | undefined,
        timestamp: typeof result['timestamp'] === 'string' ? result['timestamp'] : null,
      } as ModelResult;
    });

    return {
      qualification: 'legacy_unverified',
      totalModels: Number(data['total_models'] ?? data['models_evaluated'] ?? results.length),
      successful: Number(data['successful'] ?? results.filter((r) => r.status === 'success').length),
      failed: Number(data['failed'] ?? results.filter((r) => r.status === 'failed').length),
      skipped: Number(data['skipped'] ?? results.filter((r) => r.status === 'skipped').length),
      durationSeconds: typeof data['duration_seconds'] === 'number' ? data['duration_seconds'] : null,
      results,
      outputDir: typeof data['output_dir'] === 'string' ? data['output_dir'] : null,
    };
  }


}

/**
 * Create a new matric-eval client with default settings.
 *
 * @returns MatricEvalClient instance
 */
export function createClient(executablePath?: string): MatricEvalClient {
  return new MatricEvalClient(executablePath);
}
