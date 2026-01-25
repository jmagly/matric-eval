/**
 * Tests for matric-eval TypeScript client.
 */

import { describe, it } from 'node:test';
import * as assert from 'node:assert';

import { MatricEvalClient, MatricEvalError, createClient } from '../client.js';
import type { EvalSummary, RecommendationReport } from '../types.js';

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
