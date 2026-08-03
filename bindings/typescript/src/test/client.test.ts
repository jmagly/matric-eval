/**
 * Tests for matric-eval TypeScript client.
 */

import { describe, it } from 'node:test';
import * as assert from 'node:assert';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';

import { MatricEvalClient, MatricEvalError, createClient } from '../client.js';
import type { EvalSummary, RecommendationReport } from '../types.js';

async function createFakeExecutable(source: string): Promise<string> {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'matric-eval-client-'));
  const executable = path.join(directory, 'matric-eval');
  await fs.writeFile(executable, `#!/usr/bin/env node\n${source}\n`, { mode: 0o755 });
  return executable;
}

describe('MatricEvalClient', () => {
  describe('constructor', () => {
    it('should create client with default executable path', () => {
      const client = new MatricEvalClient();
      assert.ok(client instanceof MatricEvalClient);
    });

    it('should create client with custom executable path', () => {
      const client = new MatricEvalClient('/custom/path/matric-eval');
      assert.ok(client instanceof MatricEvalClient);
    });
  });

  describe('createClient', () => {
    it('should create client instance', () => {
      const client = createClient();
      assert.ok(client instanceof MatricEvalClient);
    });

    it('should create client with custom path', () => {
      const client = createClient('/custom/path');
      assert.ok(client instanceof MatricEvalClient);
    });
  });

  describe('CLI integration', () => {
    it('uses the current JSON option and parses benchmark mappings', async () => {
      const executable = await createFakeExecutable(`
if (process.argv.slice(2).join(' ') !== 'list-benchmarks --output-format json') {
  process.exit(2);
}
console.log(JSON.stringify({ humaneval: 'HumanEval', injecagent: 'InjecAgent' }));
`);

      const client = createClient(executable);
      assert.deepStrictEqual(await client.listBenchmarks(), ['humaneval', 'injecagent']);
    });

    it('streams subprocess output while retaining the parsed result', async () => {
      const executable = await createFakeExecutable(`
process.stdout.write('matric-eval, ');
process.stderr.write('diagnostic');
setTimeout(() => process.stdout.write('version 0.2.0\\n'), 5);
`);
      const stdout: string[] = [];
      const stderr: string[] = [];

      const version = await createClient(executable).getVersion({
        onStdout: (chunk) => stdout.push(chunk),
        onStderr: (chunk) => stderr.push(chunk),
      });

      assert.strictEqual(version, 'matric-eval, version 0.2.0');
      assert.strictEqual(stdout.join(''), 'matric-eval, version 0.2.0\n');
      assert.strictEqual(stderr.join(''), 'diagnostic');
    });

    it('passes current run arguments and parses a single-model result', async () => {
      const executable = await createFakeExecutable(`
const args = process.argv.slice(2);
const expected = ['run', '--output-format', 'json', '--tier', 'smoke', '--model', 'fixture',
  '--benchmark', 'matric_cli', '--provider', 'ollama'];
if (JSON.stringify(args) !== JSON.stringify(expected)) {
  process.stderr.write(JSON.stringify(args));
  process.exit(2);
}
console.log(JSON.stringify({ model: 'ollama/fixture', tier: 'smoke', status: 'success',
  overall_score: 0.75, benchmarks: {}, output_dir: '/tmp/run-fixture' }));
`);

      const summary = await createClient('/unused').run({
        tier: 'smoke',
        models: ['fixture'],
        benchmarks: ['matric_cli'],
        provider: 'ollama',
        executablePath: executable,
      });

      assert.strictEqual(summary.totalModels, 1);
      assert.strictEqual(summary.successful, 1);
      assert.strictEqual(summary.outputDir, '/tmp/run-fixture');
      assert.strictEqual(summary.results[0]?.model, 'fixture');
    });

    it('retains stderr and exit status for command errors', async () => {
      const executable = await createFakeExecutable(`
process.stderr.write('provider unavailable');
process.exit(7);
`);

      await assert.rejects(
        createClient(executable).listBenchmarks(),
        (error: unknown) =>
          error instanceof MatricEvalError &&
          error.exitCode === 7 &&
          error.stderr === 'provider unavailable',
      );
    });

    it('passes current recommendation arguments and normalizes score fields', async () => {
      const executable = await createFakeExecutable(`
const args = process.argv.slice(2);
const expected = ['recommend', '--results-dir', '/tmp/results', '--output-format', 'json',
  '--min-score', '0.5'];
if (JSON.stringify(args) !== JSON.stringify(expected)) {
  process.stderr.write(JSON.stringify(args));
  process.exit(2);
}
console.log(JSON.stringify({
  recommendations: { reasoning: { capability: 'reasoning', recommended: 'fixture',
    score: 0.8, alternatives: [], rationale: 'highest score' } },
  model_scores: { fixture: { model: 'fixture', benchmark_scores: { arc: 0.8 },
    capability_scores: { reasoning: 0.8 }, overall_score: 0.8, size_gb: 3 } },
  best_overall: 'fixture', best_balanced: 'fixture', metadata: { model_count: 1 }
}));
`);

      const report = await createClient(executable).recommend({
        input: '/tmp/results',
        minScore: 0.5,
      });

      assert.strictEqual(report.bestOverall, 'fixture');
      assert.strictEqual(report.modelScores['fixture']?.overallScore, 0.8);
      assert.deepStrictEqual(report.modelScores['fixture']?.benchmarkScores, { arc: 0.8 });
    });

    it('rejects options that the 0.2 CLI cannot represent', async () => {
      const client = createClient('/unused');

      await assert.rejects(
        client.run({ models: ['one', 'two'] }),
        /accepts one explicit model/,
      );
      await assert.rejects(client.run({ timeout: 30 }), /not supported/);
      await assert.rejects(client.run({ resume: true }), /requires a checkpoint/);
    });

    it('terminates the subprocess when the abort signal fires', async () => {
      const executable = await createFakeExecutable(`setInterval(() => {}, 1000);`);
      const controller = new AbortController();
      const pending = createClient(executable).getVersion({ signal: controller.signal });
      setTimeout(() => controller.abort(), 20);

      await assert.rejects(
        pending,
        (error: unknown) => error instanceof MatricEvalError && error.cancelled,
      );
    });
  });
});

describe('MatricEvalError', () => {
  it('should create error with message, exit code, and stderr', () => {
    const error = new MatricEvalError('Test error', 1, 'stderr output');
    assert.strictEqual(error.message, 'Test error');
    assert.strictEqual(error.exitCode, 1);
    assert.strictEqual(error.stderr, 'stderr output');
    assert.strictEqual(error.name, 'MatricEvalError');
  });

  it('should handle null exit code', () => {
    const error = new MatricEvalError('Test error', null, '');
    assert.strictEqual(error.exitCode, null);
  });
});

describe('Type exports', () => {
  it('should export EvalSummary type', () => {
    const summary: EvalSummary = {
      totalModels: 2,
      successful: 2,
      failed: 0,
      skipped: 0,
      durationSeconds: 120,
      results: [],
      outputDir: '/tmp/results',
    };
    assert.strictEqual(summary.totalModels, 2);
  });

  it('should export RecommendationReport type', () => {
    const report: RecommendationReport = {
      recommendations: {} as RecommendationReport['recommendations'],
      modelScores: {},
      bestOverall: 'llama3.2:3b',
      bestBalanced: 'qwen2.5:7b',
      metadata: {},
    };
    assert.strictEqual(report.bestOverall, 'llama3.2:3b');
  });
});

describe('parseEvalSummary (via loadSummary structure)', () => {
  it('should parse valid JSON structure', () => {
    // Test the expected structure of parsed data
    const mockData = {
      total_models: 3,
      successful: 2,
      failed: 1,
      skipped: 0,
      duration_seconds: 300,
      output_dir: '/tmp/results',
      results: [
        {
          model: 'ollama/llama3.2:3b',
          tier: 'smoke',
          status: 'success',
          overall_score: 0.85,
          size_gb: 2.0,
          benchmarks: {},
          timestamp: '2024-01-01T00:00:00Z',
        },
      ],
    };

    // Verify structure matches expected types
    assert.strictEqual(mockData.total_models, 3);
    assert.strictEqual(mockData.results[0]?.model, 'ollama/llama3.2:3b');
  });
});

describe('Model categories format', () => {
  it('should match matric-cli expected structure', () => {
    const config = {
      version: '1.0',
      generatedBy: 'matric-eval' as const,
      bestOverall: 'llama3.2:3b',
      categories: {
        code_generation: {
          description: 'Best for code generation',
          recommended: 'llama3.2:3b',
          alternatives: ['qwen2.5:7b'],
          score: 0.92,
        },
      },
    };

    assert.strictEqual(config.generatedBy, 'matric-eval');
    assert.strictEqual(config.categories['code_generation']?.recommended, 'llama3.2:3b');
  });
});
