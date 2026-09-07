import { describe, it } from 'node:test';
import { createHash } from 'node:crypto';
import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PARTITION_ROLES, comparisonInputs, requireComparable, logicalObservationId, readResult, validateResult, writeResult } from '../result-contract.js';
import type { ResultEnvelope, SuiteAggregation } from '../result-contract.js';
import { MatricEvalClient } from '../client.js';

const fixture = new URL('../../../../tests/fixtures/results/v2/mixed.json', import.meta.url);
function example(): ResultEnvelope { return readResult(readFileSync(fixture, 'utf8')); }
function rejectsMutation(change: (r: ResultEnvelope) => void): void {
  const r = example();
  change(r);
  assert.throws(() => validateResult(r));
  assert.throws(() => writeResult(r));
}

describe('v2 result contract', () => {
  it('round trips the shared Python fixture without losing identities, nulls, metrics, reasons or artifacts', () => {
    const raw: unknown = JSON.parse(readFileSync(fixture, 'utf8'));
    const parsed = example();
    assert.deepEqual(parsed, raw);
    assert.deepEqual(readResult(writeResult(parsed)), raw);
    assert.equal(parsed.overall_estimate.value, null);
    assert.equal(Object.keys(parsed.benchmarks[0]!.metrics).length, 2);
    assert.equal(parsed.benchmarks[0]!.observations.find(o => o.outcome === 'grader_failed')!.reason, 'position_inconsistent');
    for (const o of parsed.benchmarks[0]!.observations) assert.equal(logicalObservationId(o.identity), o.observation_id);
  });

  it('uses the same versioned partition roles for calibration and export', () => {
    const roles = JSON.parse(readFileSync(new URL('../../../../tests/fixtures/results/partition-roles.json', import.meta.url), 'utf8')) as {
      calibration_input: Array<{ partition_schema_version: string; role: string }>;
      export_input: Array<{ partition_schema_version: string; role: string }>;
    };
    assert.deepEqual(roles.calibration_input, roles.export_input);
    assert.deepEqual(roles.calibration_input.map(r => r.role), [...PARTITION_ROLES]);
    const schema = JSON.parse(readFileSync(new URL('../../../../schemas/evaluation-result-v2.schema.json', import.meta.url), 'utf8')) as {
      $defs: { DataReference: { properties: { role: { enum: string[] }; partition_schema_version: { const: string } } } };
    };
    assert.deepEqual(schema.$defs.DataReference.properties.role.enum, [...PARTITION_ROLES]);
    assert.equal(schema.$defs.DataReference.properties.partition_schema_version.const, '1');
    for (const role of roles.calibration_input) {
      assert.equal(role.partition_schema_version, '1');
      const r = example();
      Object.assign(r.benchmarks[0]!.selection[0]!.data, role);
      validateResult(r);
    }
  });

  it('rejects unsupported versions, unknown fields, coercions and nested malformed records', () => {
    for (const change of [
      (r: ResultEnvelope) => Object.assign(r, { result_schema_version: '3' }),
      (r: ResultEnvelope) => Object.assign(r, { result_schema_version: 2 }),
      (r: ResultEnvelope) => Object.assign(r, { surprise: 1 }),
      (r: ResultEnvelope) => Object.assign(r.benchmarks[0]!.coverage, { requested: '9' }),
      (r: ResultEnvelope) => Object.assign(r.benchmarks[0]!.coverage, { requested: true }),
      (r: ResultEnvelope) => Object.assign(r.benchmarks[0]!.selection[0]!.data, { role: 'holdout' }),
      (r: ResultEnvelope) => Object.assign(r.benchmarks[0]!.selection[0]!.data, { partition_schema_version: '2' }),
      (r: ResultEnvelope) => Object.assign(r.benchmarks[0]!.observations[0]!, { value: false }),
      (r: ResultEnvelope) => Object.assign(r, { run_id: '   ' }),
      (r: ResultEnvelope) => Object.assign(r, { configuration_sha256: 'bad' }),
    ]) rejectsMutation(change);
  });

  it('rejects nonfinite input tokens and serialization instead of converting them to null', () => {
    for (const token of ['NaN', 'Infinity', '-Infinity', '1e999']) {
      const payload = readFileSync(fixture, 'utf8').replace('"value": null', `"value": ${token}`);
      assert.throws(() => readResult(payload));
    }
    for (const n of [NaN, Infinity, -Infinity]) {
      rejectsMutation(r => { r.benchmarks[0]!.metrics['rubric/points']!.descriptor.maximum = n; });
      rejectsMutation(r => { r.benchmarks[0]!.observations[0]!.value = n; });
      rejectsMutation(r => { r.overall_estimate.denominator = n; });
    }
  });

  it('rejects identity, coverage, primary metric and missingness contradictions', () => {
    for (const change of [
      (r: ResultEnvelope) => { r.benchmarks[0]!.observations[0]!.identity.run_id = 'different'; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.observations.push(structuredClone(r.benchmarks[0]!.observations[0]!)); },
      (r: ResultEnvelope) => { r.benchmarks[0]!.observations.pop(); },
      (r: ResultEnvelope) => { r.benchmarks[0]!.selection.push(structuredClone(r.benchmarks[0]!.selection[0]!)); },
      (r: ResultEnvelope) => { r.benchmarks[0]!.coverage.attempted++; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.primary_metric_id = 'missing'; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.metrics['exact/accuracy']!.scored++; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.metrics['rubric/points']!.estimate.value = 6; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.metrics['exact/accuracy']!.outcome_counts.observed = 3; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.observations.find(o => o.outcome === 'grader_failed')!.value = 0; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.observations.find(o => o.outcome === 'model_timeout')!.value = null; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.observations[0]!.artifacts[0]!.unavailable_reason = 'unknown'; },
      (r: ResultEnvelope) => { r.benchmarks[0]!.execution = 'completed'; },
      (r: ResultEnvelope) => { r.execution = 'completed'; },
      (r: ResultEnvelope) => { r.eligibility = { eligible: true, reasons: [] }; },
    ]) rejectsMutation(change);
  });

  it('rejects benchmark eligibility when all records are terminal but some samples failed', () => {
    const r = example();
    const b = r.benchmarks[0]!;
    const remove = new Set(b.observations.filter(o => o.execution === 'not_attempted' || o.execution === 'unknown').map(o => o.identity.sample_id));
    b.selection = b.selection.filter(s => !remove.has(s.sample_id));
    b.observations = b.observations.filter(o => !remove.has(o.identity.sample_id));
    b.coverage.requested = 7;
    b.coverage.not_attempted = 0;
    b.coverage.unknown = 0;
    b.execution = 'completed';
    for (const m of Object.values(b.metrics)) {
      m.outcome_counts.not_attempted = 0;
      m.outcome_counts.legacy_unknown = 0;
    }
    validateResult(r);
    b.eligibility = { eligible: true, reasons: [] };
    b.primary_estimate.eligibility = { eligible: true, reasons: [] };
    b.metrics[b.primary_metric_id!]!.estimate = structuredClone(b.primary_estimate);
    assert.throws(() => validateResult(r), /completed samples/);
  });

  it('retains superseded attempts without increasing selected or scored counts', () => {
    const r = example();
    const b = r.benchmarks[0]!;
    const accepted = b.observations[0]!;
    const previous = structuredClone(accepted);
    previous.accepted = false;
    previous.attempt_id = 'attempt-0';
    previous.outcome = 'infrastructure_error';
    previous.execution = 'failed';
    previous.value = null;
    previous.reason = 'transient-backend';
    accepted.previous_attempt_id = previous.attempt_id;
    b.observations.unshift(previous);
    validateResult(r);
    assert.equal(b.coverage.requested, 9);
    assert.equal(b.metrics['exact/accuracy']!.scored, 3);
    assert.deepEqual(readResult(writeResult(r)), r);
    previous.accepted = true;
    assert.throws(() => validateResult(r));
  });

  it('rejects versioned records at the legacy client boundary before null-to-zero projection', () => {
    // Exercise the existing private wire parser without spawning a provider/CLI.
    const client = new MatricEvalClient() as unknown as { parseEvalSummary(json: string): unknown };
    for (const version of ['2', '3']) {
      assert.throws(() => client.parseEvalSummary(JSON.stringify({ result_schema_version: version, overall_score: null })), /invalid_versioned_result|unsupported_schema|unrecognized_legacy_shape/);
      assert.throws(() => client.parseEvalSummary(JSON.stringify({ results: [{ result_schema_version: version, overall_score: null }] })), /invalid_versioned_result|unsupported_schema|unrecognized_legacy_shape/);
    }
    assert.throws(() => client.parseEvalSummary(JSON.stringify({ results: [{ model: 'model', status: 'success', overall_score: null }] })), /unrecognized_legacy_shape|legacy_projection_unrepresentable/);
  });
});

function declaredPolicy(): SuiteAggregation {
  return {
    version: '1', aggregation_id: 'example/1', target_units: 'fraction', target_direction: 'higher',
    missingness_policy: 'require-complete', terms: [{ benchmark_id: 'example', metric_id: 'exact/accuracy', weight: 1,
      transform: { version: '1', kind: 'identity', source_units: 'fraction', source_minimum: 0,
        source_maximum: 1, source_direction: 'higher', scale: 1, offset: 0 } }],
  };
}
function attachTestComparison(r: ResultEnvelope): void {
  const payload = JSON.stringify(comparisonInputs(r));
  const reasons: string[] = [];
  if (r.configuration_sha256 === null) reasons.push('comparison_configuration_unverified');
  if (!r.eligibility.eligible) reasons.push('measurement_scope_ineligible');
  if (r.aggregation != null && !r.overall_estimate.eligibility.eligible) reasons.push('aggregate_ineligible');
  for (const b of r.benchmarks) {
    if (b.protocol_sha256 === null || b.manifest_sha256 === null) reasons.push(`protocol_or_manifest_unverified:${b.benchmark_id}`);
    if (b.selection.some(s => s.data.role === 'unknown')) reasons.push(`partition_role_unknown:${b.benchmark_id}`);
  }
  r.comparability = { version: '1', payload, sha256: createHash('sha256').update(payload, 'utf8').digest('hex'), eligibility: { eligible: reasons.length === 0, reasons } };
}
describe('named metrics and comparison declarations', () => {
  it('round trips the shared native named-metric fixture and its Python comparison payload', () => {
    const wire = readFileSync(new URL('../../../../tests/fixtures/results/v2/named-metrics.json', import.meta.url), 'utf8');
    const raw: unknown = JSON.parse(wire);
    const r = readResult(wire);
    assert.deepEqual(r, raw);
    assert.deepEqual(readResult(writeResult(r)), raw);
    const b = r.benchmarks[0]!;
    assert.equal(b.primary_metric_id, 'exact/accuracy');
    assert.equal(b.primary_estimate.value, 0.5);
    assert.equal(b.metrics['exact/stderr']!.estimate.value, 0.5);
    assert.equal(b.metrics['exact/stderr']!.observation_metric_id, 'exact/accuracy');
    assert.equal(b.metrics['exact/stderr']!.estimate.denominator, null);
    assert.equal(b.observations.length, 2);
    assert.ok(b.observations.every(o => o.identity.metric_id === 'exact/accuracy'));
    assert.equal(r.comparability!.eligibility.eligible, false);
    assert.ok(r.comparability!.eligibility.reasons.includes('partition_role_unknown:benchmark'));
    assert.throws(() => requireComparable(r, structuredClone(r)), /unverified or ineligible/);
  });

  it('retains derived stderr without inventing per-sample stderr grades', () => {
    const r = example();
    const b = r.benchmarks[0]!;
    const derived = structuredClone(b.metrics['exact/accuracy']!);
    derived.descriptor.metric_id = 'exact/stderr';
    derived.observation_metric_id = 'exact/accuracy';
    derived.native_estimate = 0.15;
    derived.estimate.value = 0.15;
    b.metrics['exact/stderr'] = derived;
    validateResult(r);
    assert.deepEqual(readResult(writeResult(r)), r);
    assert.equal(b.observations.filter(o => o.identity.metric_id === 'exact/stderr').length, 0);
    for (const source of ['missing', 'exact/stderr', 'rubric/points']) {
      derived.observation_metric_id = source;
      assert.throws(() => validateResult(r));
    }
    derived.observation_metric_id = 'exact/accuracy';
    const fake = structuredClone(b.observations[0]!);
    fake.identity.metric_id = 'exact/stderr';
    fake.observation_id = logicalObservationId(fake.identity);
    b.observations.push(fake);
    assert.throws(() => validateResult(r), /derived metric/);
  });

  it('validates explicit aggregation weights, units, bounds and directional transforms', () => {
    const r = example();
    r.aggregation = declaredPolicy();
    r.aggregation_id = r.aggregation.aggregation_id;
    validateResult(r);
    const mutations: Array<(p: SuiteAggregation) => void> = [
      p => { p.terms[0]!.weight = 0; }, p => { p.terms[0]!.weight = -1; },
      p => { p.terms[0]!.weight = Infinity; }, p => { p.terms = []; },
      p => { p.terms.push(structuredClone(p.terms[0]!)); },
      p => { p.terms[0]!.transform.scale = 0; }, p => { p.terms[0]!.transform.offset = 1; },
      p => { p.terms[0]!.transform.source_minimum = 2; },
      p => { p.target_units = 'points'; }, p => { p.target_direction = 'lower'; },
      p => { p.terms[0]!.transform.kind = 'affine'; p.terms[0]!.transform.scale = -1; },
      p => { Object.assign(p.terms[0]!.transform, { unknown: true }); },
    ];
    for (const mutate of mutations) {
      r.aggregation = declaredPolicy(); mutate(r.aggregation);
      assert.throws(() => validateResult(r));
    }
    r.aggregation = declaredPolicy();
    Object.assign(r.aggregation.terms[0]!.transform, { kind: 'affine', source_direction: 'lower', scale: -0.1, offset: 1, source_units: 'seconds' });
    validateResult(r);
    r.aggregation_id = 'mismatch';
    assert.throws(() => validateResult(r), /identity differs/);
  });

  it('verifies comparison digest, scope and eligibility without trusting an identity label', () => {
    const r = example(); attachTestComparison(r); validateResult(r);
    assert.deepEqual(readResult(writeResult(r)), r);
    assert.throws(() => requireComparable(r, structuredClone(r)), /ineligible/);
    const broken = structuredClone(r);
    broken.comparability!.payload += ' ';
    assert.throws(() => validateResult(broken), /digest differs/);
    const changed = structuredClone(r);
    changed.benchmarks[0]!.selection[0]!.data.source_id = 'changed scope';
    assert.throws(() => validateResult(changed), /scope/);
    const forged = structuredClone(r);
    forged.comparability!.eligibility = { eligible: true, reasons: [] };
    assert.throws(() => validateResult(forged), /eligibility differs/);
    const changedMetric = structuredClone(r);
    changedMetric.benchmarks[0]!.metrics['exact/accuracy']!.descriptor.version = 'new';
    assert.throws(() => validateResult(changedMetric), /scope/);
  });
});
