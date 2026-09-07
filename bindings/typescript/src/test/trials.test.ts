import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { logicalObservationId, readResult } from '../result-contract.js';
import type { ResultEstimate } from '../result-contract.js';
import { readTrials, trialManifestDigest, validateTrials, writeTrials } from '../trials.js';
import type { TrialEvaluation, TrialRecord } from '../trials.js';

function estimate(value: number, method: string, numerator: number | null = null, denominator: number | null = null): ResultEstimate {
  return { value, method, numerator, denominator, reason: null, eligibility: { eligible: true, reasons: [] } };
}
function missing(method: string): ResultEstimate {
  return { value: null, method, numerator: null, denominator: null, reason: 'missing_task_trials', eligibility: { eligible: false, reasons: ['missing_task_trials'] } };
}
function example(): TrialEvaluation {
  const source = readResult(readFileSync(new URL('../../../../tests/fixtures/results/v2/named-metrics.json', import.meta.url), 'utf8'));
  const manifest = structuredClone(source.benchmarks[0]!.selection);
  for (const row of manifest) row.trial_id = 'selected';
  const trials: TrialRecord[] = [0, 1].map(i => {
    const b = structuredClone(source.benchmarks[0]!);
    for (const row of b.selection) row.trial_id = `trial-${i}`;
    for (const row of b.observations) {
      row.identity.trial_id = `trial-${i}`;
      row.observation_id = logicalObservationId(row.identity);
      if (i === 1) row.value = 1 - row.value!;
    }
    return { trial_id: `trial-${i}`, generation_seed: 100 + i, benchmark: b, unavailable_reason: null,
      native_trial_id: 'epoch-1', generation_evidence: null };
  });
  return {
    trial_schema_version: '1', run_id: source.run_id, model_id: source.model_id, benchmark_id: source.benchmarks[0]!.benchmark_id,
    protocol: { version: '1', n: 2, k: 2, metric_id: 'exact/accuracy', metric_version: '1',
      predicate: { version: '1', kind: 'equals', threshold: 1, units: 'fraction' }, generation_seeds: [100, 101],
      root_generation_seed: 99, selection_seed: 42, task_content_sha256: 'c'.repeat(64), independence: 'unverified', statistical_claim: 'descriptive_only' },
    manifest, manifest_sha256: trialManifestDigest(manifest), trials,
    per_task: manifest.map(s => ({ allocation_id: s.allocation_id, sample_id: s.sample_id, n_requested: 2, n_observed: 2, c: 1,
      pass_at_k: estimate(1, 'pass-at-2/1'), all_n_success: estimate(0, 'all-n-success/1') })),
    macro_pass_at_k: estimate(1, 'task-macro-pass-at-k/1', 2, 2), macro_all_n_success: estimate(0, 'task-macro-all-n-success/1', 0, 2),
    execution: 'completed', eligibility: { eligible: true, reasons: [] },
    limitations: ['statistical_independence_unverified', 'descriptive_statistics_only', 'generation_evidence_unavailable:trial-0', 'generation_evidence_unavailable:trial-1'],
  };
}

describe('aligned trial records', () => {
  it('round trips the Python trial fixture with independent counts and distinct logical identities', () => {
    const wire = readFileSync(new URL('../../../../tests/fixtures/results/trials/disjoint.json', import.meta.url), 'utf8');
    const raw: unknown = JSON.parse(wire);
    const r = readTrials(wire);
    assert.deepEqual(r, raw);
    assert.deepEqual(readTrials(writeTrials(r)), raw);
    assert.deepEqual(r.per_task.map(t => [t.n_requested, t.n_observed, t.c]), [[2, 2, 1], [2, 2, 1]]);
    assert.ok(r.per_task.every(t => t.pass_at_k.value === 1 && t.all_n_success.value === 0));
    assert.equal(r.macro_pass_at_k.value, 1);
    assert.equal(r.macro_all_n_success.value, 0);
    const rows = r.trials.flatMap(t => t.benchmark?.observations ?? []);
    assert.equal(rows.length, 4);
    assert.equal(new Set(rows.map(o => o.observation_id)).size, rows.length);
    for (const row of rows) assert.equal(row.observation_id, logicalObservationId(row.identity));
    assert.equal(r.manifest_sha256, trialManifestDigest(r.manifest));
  });

  it('preserves disjoint task successes as pass@2=1 and observed all-success=0', () => {
    const r = example();
    validateTrials(r);
    assert.deepEqual(readTrials(writeTrials(r)), r);
    assert.equal(r.macro_pass_at_k.value, 1);
    assert.equal(r.macro_all_n_success.value, 0);
    assert.deepEqual(r.per_task.map(t => [t.n_requested, t.n_observed, t.c]), [[2, 2, 1], [2, 2, 1]]);
  });

  it('keeps missing trial denominators and null estimates explicit', () => {
    const r = example();
    r.trials[1]!.benchmark = null;
    r.trials[1]!.unavailable_reason = 'trial_not_returned';
    for (const [i, t] of r.per_task.entries()) {
      t.n_observed = 1; t.c = i === 0 ? 1 : 0;
      t.pass_at_k = missing('pass-at-2/1'); t.all_n_success = missing('all-n-success/1');
    }
    r.macro_pass_at_k = missing('task-macro-pass-at-k/1'); r.macro_all_n_success = missing('task-macro-all-n-success/1');
    r.execution = 'partial'; r.eligibility = { eligible: false, reasons: ['incomplete_trial_execution', 'missing_task_trials'] };
    validateTrials(r);
    assert.deepEqual(readTrials(writeTrials(r)), r);
    r.per_task[0]!.n_requested = 1;
    assert.throws(() => validateTrials(r), /n_requested/);
  });

  it('retains retries without counting them as independent draws', () => {
    const r = example();
    const b = r.trials[0]!.benchmark!;
    const previous = structuredClone(b.observations[0]!);
    previous.attempt_id = 'prior'; previous.accepted = false; previous.execution = 'failed';
    previous.outcome = 'infrastructure_error'; previous.value = null; previous.reason = 'retry';
    b.observations[0]!.previous_attempt_id = 'prior'; b.observations.unshift(previous);
    validateTrials(r);
    assert.equal(r.per_task[0]!.n_observed, 2);
    assert.equal(r.trials[0]!.benchmark!.observations.length, 3);
  });

  it('rejects forged counts, missing or reordered trials, changed scopes and invalid seeds', () => {
    const mutations: Array<(r: TrialEvaluation) => void> = [
      r => { r.per_task[0]!.c = 2; }, r => { r.per_task[0]!.n_observed = 3; },
      r => { r.macro_all_n_success.value = 1; }, r => { r.trials.pop(); },
      r => { r.trials.reverse(); }, r => { r.trials[1]!.trial_id = 'trial-0'; },
      r => { r.protocol.k = 3; }, r => { r.protocol.generation_seeds = [100, 100]; },
      r => { r.protocol.generation_seeds = [100]; }, r => { r.trials[0]!.generation_seed = 0; },
      r => { r.protocol.root_generation_seed = Number.MAX_SAFE_INTEGER + 1; },
      r => { r.manifest[0]!.data.source_id = 'changed'; },
      r => { r.trials[1]!.benchmark!.selection.reverse(); },
      r => { r.trials[1]!.benchmark!.metrics['exact/accuracy']!.descriptor.maximum = 2; },
      r => { r.trials[1]!.benchmark!.metrics['exact/accuracy']!.descriptor.missingness_policy = 'changed'; },
      r => { r.protocol.metric_version = '2'; }, r => { r.protocol.predicate.units = 'points'; },
      r => { r.protocol.metric_id = 'exact/stderr'; },
      r => { Object.assign(r.protocol, { independence: 'verified' }); },
      r => { Object.assign(r.protocol, { statistical_claim: 'inferential' }); },
      r => { Object.assign(r, { trial_schema_version: '2' }); },
      r => { Object.assign(r.protocol, { n: true }); }, r => { Object.assign(r.trials[0]!, { unknown: 1 }); },
      r => { r.trials[0]!.benchmark!.observations[0]!.value = NaN; },
    ];
    for (const mutate of mutations) {
      const r = example(); mutate(r);
      assert.throws(() => validateTrials(r)); assert.throws(() => writeTrials(r));
    }
  });

  it('retains descriptive values while propagating ineligible benchmark measurements', () => {
    const r = example();
    r.trials[1]!.benchmark!.eligibility = { eligible: false, reasons: ['measurement_unqualified'] };
    assert.throws(() => validateTrials(r));
    const eligibility = { eligible: false, reasons: ['benchmark_measurement_ineligible'] };
    r.eligibility = structuredClone(eligibility);
    for (const t of r.per_task) {
      t.pass_at_k.eligibility = structuredClone(eligibility);
      t.all_n_success.eligibility = structuredClone(eligibility);
    }
    r.macro_pass_at_k.eligibility = structuredClone(eligibility);
    r.macro_all_n_success.eligibility = structuredClone(eligibility);
    validateTrials(r);
    assert.equal(r.execution, 'completed');
    assert.equal(r.macro_pass_at_k.value, 1);
    assert.equal(r.macro_all_n_success.value, 0);
  });

  it('preserves failed native executions and trial artifacts without reporting partial completion', () => {
    const r = example();
    const reasons = ['incomplete_trial_execution', 'benchmark_measurement_ineligible'];
    for (const t of r.trials) {
      t.benchmark!.execution = 'failed';
      t.benchmark!.eligibility = { eligible: false, reasons: ['native_error'] };
      t.failure_code = 'native_error';
      t.artifacts = [{ uri: 'inspect:native-error', sha256: null, unavailable_reason: 'not_local' }];
    }
    for (const t of r.per_task) {
      t.pass_at_k.eligibility = { eligible: false, reasons };
      t.all_n_success.eligibility = { eligible: false, reasons };
    }
    r.macro_pass_at_k.eligibility = { eligible: false, reasons };
    r.macro_all_n_success.eligibility = { eligible: false, reasons };
    r.execution = 'failed'; r.eligibility = { eligible: false, reasons };
    validateTrials(r);
    assert.deepEqual(readTrials(writeTrials(r)), r);
    assert.equal(r.macro_pass_at_k.value, 1);
    r.execution = 'partial';
    assert.throws(() => validateTrials(r), /execution/);
    r.execution = 'failed';
    r.trials[0]!.artifacts![0]!.unavailable_reason = null;
    assert.throws(() => validateTrials(r), /artifact/);
  });

  it('records seed forwarding without upgrading it to honored or independent generation', () => {
    const r = example();
    r.trials[0]!.generation_evidence = { requested_seed: 100, recorded_seed: 100, temperature: 0,
      provider_id: 'ollama', forwarding: 'recorded', honored: 'unverified', limitations: ['deterministic_decoding'] };
    r.limitations = ['statistical_independence_unverified', 'descriptive_statistics_only', 'trial-0:deterministic_decoding',
      'generation_seed_honoring_unverified:trial-0', 'generation_evidence_unavailable:trial-1'];
    validateTrials(r);
    r.trials[0]!.generation_evidence.recorded_seed = 999;
    assert.throws(() => validateTrials(r), /matching/);
    r.trials[0]!.generation_evidence.recorded_seed = 100;
    Object.assign(r.trials[0]!.generation_evidence, { honored: 'verified' });
    assert.throws(() => validateTrials(r));
  });
});
