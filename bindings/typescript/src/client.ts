/**
 * TypeScript client for matric-eval evaluation framework.
 *
 * Provides a programmatic interface to invoke the matric-eval CLI
 * and parse results for use in TypeScript/JavaScript applications.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';

import type {
  BenchmarkId,
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
 *   models: ['llama3.2:3b', 'qwen2.5:7b'],
 * });
 *
 * // Generate recommendations
 * const report = await client.recommend({
 *   input: summary.outputDir,
 * });
 *
 * // Export for matric-cli
 * await client.exportModelCategories(report, 'model-categories.json');
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
  private async execute(args: string[]): Promise<CommandResult> {
    return new Promise((resolve, reject) => {
      const proc: ChildProcess = spawn(this.executablePath, args, {
        stdio: ['inherit', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';

      proc.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      proc.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      proc.on('error', (error) => {
        reject(new MatricEvalError(`Failed to execute matric-eval: ${error.message}`, null, ''));
      });

      proc.on('close', (code) => {
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
  async isAvailable(): Promise<boolean> {
    try {
      const result = await this.execute(['--version']);
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
  async getVersion(): Promise<string> {
    const result = await this.execute(['--version']);
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
  async listModels(): Promise<string[]> {
    const result = await this.execute(['list-models', '--format', 'json']);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Failed to list models', result.exitCode, result.stderr);
    }

    const data = JSON.parse(result.stdout) as { models: Array<{ name: string }> };
    return data.models.map((m) => m.name);
  }

  /**
   * List available benchmarks.
   *
   * @param tier - Optional tier to filter benchmarks
   * @returns Array of benchmark identifiers
   */
  async listBenchmarks(tier?: EvalTier): Promise<BenchmarkId[]> {
    const args = ['list-benchmarks', '--format', 'json'];
    if (tier) {
      args.push('--tier', tier);
    }

    const result = await this.execute(args);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Failed to list benchmarks', result.exitCode, result.stderr);
    }

    const data = JSON.parse(result.stdout) as { benchmarks: Array<{ name: string }> };
    return data.benchmarks.map((b) => b.name as BenchmarkId);
  }

  /**
   * Run an evaluation.
   *
   * @param options - Evaluation options
   * @returns Evaluation summary
   */
  async run(options: EvalOptions = {}): Promise<EvalSummary> {
    const args = ['run', '--format', 'json'];

    if (options.tier) {
      args.push('--tier', options.tier);
    }

    if (options.models && options.models.length > 0) {
      for (const model of options.models) {
        args.push('--model', model);
      }
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

    if (options.timeout !== undefined) {
      args.push('--timeout', options.timeout.toString());
    }

    if (options.parallelism !== undefined) {
      args.push('--parallel', options.parallelism.toString());
    }

    if (options.resume) {
      args.push('--resume');
    }

    if (options.logLevel) {
      args.push('--log-level', options.logLevel);
    }

    const result = await this.execute(args);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Evaluation failed', result.exitCode, result.stderr);
    }

    return this.parseEvalSummary(result.stdout);
  }

  /**
   * Generate recommendations from evaluation results.
   *
   * @param options - Recommendation options
   * @returns Recommendation report
   */
  async recommend(options: RecommendOptions): Promise<RecommendationReport> {
    const args = ['recommend', '--input', options.input, '--format', 'json'];

    if (options.output) {
      args.push('--output', options.output);
    }

    if (options.minScore !== undefined) {
      args.push('--min-score', options.minScore.toString());
    }

    const result = await this.execute(args);
    if (result.exitCode !== 0) {
      throw new MatricEvalError('Failed to generate recommendations', result.exitCode, result.stderr);
    }

    return JSON.parse(result.stdout) as RecommendationReport;
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
    report: RecommendationReport,
    outputPath: string,
  ): Promise<void> {
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
    const data = JSON.parse(json) as Record<string, unknown>;

    const results: ModelResult[] = ((data['results'] as unknown[]) ?? []).map((r) => {
      const result = r as Record<string, unknown>;
      return {
        model: String(result['model'] ?? '').replace('ollama/', ''),
        tier: (result['tier'] as EvalTier) ?? 'smoke',
        status: (result['status'] as 'success' | 'failed' | 'skipped') ?? 'failed',
        overallScore: Number(result['overall_score'] ?? 0),
        sizeGb: Number(result['size_gb'] ?? 0),
        benchmarks: (result['benchmarks'] as Record<BenchmarkId, unknown>) ?? {},
        error: result['error'] as string | undefined,
        timestamp: String(result['timestamp'] ?? new Date().toISOString()),
      } as ModelResult;
    });

    return {
      totalModels: Number(data['total_models'] ?? results.length),
      successful: Number(data['successful'] ?? results.filter((r) => r.status === 'success').length),
      failed: Number(data['failed'] ?? results.filter((r) => r.status === 'failed').length),
      skipped: Number(data['skipped'] ?? results.filter((r) => r.status === 'skipped').length),
      durationSeconds: Number(data['duration_seconds'] ?? 0),
      results,
      outputDir: String(data['output_dir'] ?? ''),
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
