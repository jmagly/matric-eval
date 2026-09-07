/** Opt-in v2 records. Wire names and nulls are preserved without legacy projection. */
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';

export type ResultExecution = 'completed' | 'partial' | 'failed' | 'cancelled' | 'not_attempted' | 'unknown';
export type ResultOutcome = 'observed' | 'model_timeout' | 'infrastructure_error' | 'grader_failed' | 'cancelled' | 'not_attempted' | 'unavailable' | 'legacy_unknown';
export const PARTITION_ROLES = ['development', 'validation', 'calibration', 'final_test', 'training', 'unknown'] as const;
export type PartitionRole = typeof PARTITION_ROLES[number];
export interface ArtifactReference { uri: string; sha256: string | null; unavailable_reason: string | null }
export interface DataReference { partition_schema_version: '1'; role: PartitionRole; row_id: string; source_id: string; independent_unit_id: string }
export interface ResultEligibility { eligible: boolean; reasons: string[] }
export interface MetricDescriptor {
  metric_id: string; version: string; scorer_id: string; value_kind: 'binary' | 'continuous' | 'count';
  units: string; direction: 'higher' | 'lower' | 'neutral'; minimum: number | null; maximum: number | null;
  independent_unit: string; missingness_policy: string; aggregation_id: string | null; timeout_value: number | null;
}
export interface JudgeIdentity { judge_id: string; configuration_sha256: string; reversal_policy: string; retry_policy: string; calibration: ArtifactReference | null }
export interface ResultSelection { allocation_id: string; sample_id: string; trial_id: string; data: DataReference }
export interface ObservationIdentity { run_id: string; model_id: string; benchmark_id: string; allocation_id: string; sample_id: string; trial_id: string; metric_id: string }
export interface ResultObservation {
  observation_id: string; identity: ObservationIdentity; attempt_id: string; previous_attempt_id: string | null;
  accepted: boolean; execution: ResultExecution; outcome: ResultOutcome; value: number | null; reason: string | null;
  native_status: string; judge: JudgeIdentity | null; artifacts: ArtifactReference[];
}
export interface ResultEstimate { value: number | null; reason: string | null; numerator: number | null; denominator: number | null; method: string; eligibility: ResultEligibility }
export interface ResultCoverage { requested: number; attempted: number; terminal: number; completed: number; failed: number; cancelled: number; not_attempted: number; unknown: number }
export interface NamedMetricResult { descriptor: MetricDescriptor; estimate: ResultEstimate; scored: number; outcome_counts: Partial<Record<ResultOutcome, number>> }
export interface BenchmarkResultV2 {
  benchmark_id: string; protocol_sha256: string | null; manifest_sha256: string | null;
  execution: ResultExecution; eligibility: ResultEligibility; primary_metric_id: string | null;
  primary_estimate: ResultEstimate; metrics: Record<string, NamedMetricResult>; selection: ResultSelection[];
  observations: ResultObservation[]; coverage: ResultCoverage; artifacts: ArtifactReference[];
}
export interface ResultEnvelope {
  result_schema_version: '2'; run_id: string; model_id: string; created_at: string; provenance_schema_version: string;
  configuration_sha256: string | null; execution: ResultExecution; eligibility: ResultEligibility;
  benchmarks: BenchmarkResultV2[]; aggregation_id: string | null; overall_estimate: ResultEstimate; artifacts: ArtifactReference[];
}

type Check = (value: unknown, path: string) => void;
function requireThat(condition: boolean, message: string): asserts condition {
  if (!condition) throw new TypeError(message);
}
const text: Check = (v, p) => requireThat(typeof v === 'string' && /\S/u.test(v), `${p} must be nonempty text`);
const digest: Check = (v, p) => requireThat(typeof v === 'string' && /^[a-f0-9]{64}$/u.test(v), `${p} must be a SHA-256 digest`);
const number: Check = (v, p) => requireThat(typeof v === 'number' && Number.isFinite(v), `${p} must be a finite number`);
const count: Check = (v, p) => requireThat(typeof v === 'number' && Number.isSafeInteger(v) && v >= 0, `${p} must be a nonnegative safe integer`);
const boolean: Check = (v, p) => requireThat(typeof v === 'boolean', `${p} must be boolean`);
const nullable = (check: Check): Check => (v, p) => { if (v !== null) check(v, p); };
const enumeration = (values: readonly string[]): Check => (v, p) => requireThat(typeof v === 'string' && values.includes(v), `${p} has an unsupported value`);
const array = (check: Check): Check => (v, p) => {
  requireThat(Array.isArray(v), `${p} must be an array`);
  for (let i = 0; i < v.length; i++) check(v[i], `${p}[${i}]`);
};
function record(v: unknown, p: string): asserts v is Record<string, unknown> {
  requireThat(v !== null && typeof v === 'object' && !Array.isArray(v) &&
    (Object.getPrototypeOf(v) === Object.prototype || Object.getPrototypeOf(v) === null), `${p} must be an object`);
}
const object = (fields: Record<string, Check>): Check => (v, p) => {
  record(v, p);
  requireThat(Object.keys(v).length === Object.keys(fields).length && Object.keys(v).every(k => Object.hasOwn(fields, k)), `${p} has missing or unknown fields`);
  for (const [key, check] of Object.entries(fields)) {
    requireThat(Object.hasOwn(v, key), `${p}.${key} is required`);
    check(v[key], `${p}.${key}`);
  }
};
const dictionary = (keyCheck: Check, valueCheck: Check): Check => (v, p) => {
  record(v, p);
  for (const [key, value] of Object.entries(v)) { keyCheck(key, `${p} key`); valueCheck(value, `${p}.${key}`); }
};
const execution = enumeration(['completed', 'partial', 'failed', 'cancelled', 'not_attempted', 'unknown']);
const outcome = enumeration(['observed', 'model_timeout', 'infrastructure_error', 'grader_failed', 'cancelled', 'not_attempted', 'unavailable', 'legacy_unknown']);
const artifact = object({ uri: text, sha256: nullable(digest), unavailable_reason: nullable(text) });
const data = object({ partition_schema_version: enumeration(['1']), role: enumeration(PARTITION_ROLES), row_id: text, source_id: text, independent_unit_id: text });
const eligibility = object({ eligible: boolean, reasons: array(text) });
const descriptor = object({ metric_id: text, version: text, scorer_id: text, value_kind: enumeration(['binary', 'continuous', 'count']), units: text, direction: enumeration(['higher', 'lower', 'neutral']), minimum: nullable(number), maximum: nullable(number), independent_unit: text, missingness_policy: text, aggregation_id: nullable(text), timeout_value: nullable(number) });
const judge = object({ judge_id: text, configuration_sha256: digest, reversal_policy: text, retry_policy: text, calibration: nullable(artifact) });
const selection = object({ allocation_id: text, sample_id: text, trial_id: text, data });
const identity = object({ run_id: text, model_id: text, benchmark_id: text, allocation_id: text, sample_id: text, trial_id: text, metric_id: text });
const observation = object({ observation_id: digest, identity, attempt_id: text, previous_attempt_id: nullable(text), accepted: boolean, execution, outcome, value: nullable(number), reason: nullable(text), native_status: text, judge: nullable(judge), artifacts: array(artifact) });
const estimate = object({ value: nullable(number), reason: nullable(text), numerator: nullable(number), denominator: nullable(number), method: text, eligibility });
const coverage = object({ requested: count, attempted: count, terminal: count, completed: count, failed: count, cancelled: count, not_attempted: count, unknown: count });
const metric = object({ descriptor, estimate, scored: count, outcome_counts: dictionary(outcome, count) });
const benchmark = object({ benchmark_id: text, protocol_sha256: nullable(digest), manifest_sha256: nullable(digest), execution, eligibility, primary_metric_id: nullable(text), primary_estimate: estimate, metrics: dictionary(text, metric), selection: array(selection), observations: array(observation), coverage, artifacts: array(artifact) });
const envelope = object({ result_schema_version: enumeration(['2']), run_id: text, model_id: text, created_at: text, provenance_schema_version: text, configuration_sha256: nullable(digest), execution, eligibility, benchmarks: array(benchmark), aggregation_id: nullable(text), overall_estimate: estimate, artifacts: array(artifact) });

/** Stable logical identity excludes the execution attempt, matching Python's UTF-8 JSON array. */
export function logicalObservationId(id: ObservationIdentity): string {
  identity(id, 'identity');
  return createHash('sha256').update(JSON.stringify([id.run_id, id.model_id, id.benchmark_id, id.allocation_id, id.sample_id, id.trial_id, id.metric_id]), 'utf8').digest('hex');
}
function selectionKey(s: Pick<ResultSelection, 'allocation_id' | 'sample_id' | 'trial_id'>): string {
  return JSON.stringify([s.allocation_id, s.sample_id, s.trial_id]);
}
function checkArtifact(a: ArtifactReference): void {
  requireThat((a.sha256 === null) === (a.unavailable_reason !== null), 'artifact needs either digest or unavailable reason');
}
function checkEligibility(e: ResultEligibility): void {
  requireThat(e.eligible !== (e.reasons.length > 0), 'eligible results have no reasons; ineligible results require reasons');
}
function checkEstimate(e: ResultEstimate): void {
  checkEligibility(e.eligibility);
  requireThat((e.value === null) === (e.reason !== null), 'null estimate requires reason; measured estimate has no reason');
  requireThat(e.value !== null || !e.eligibility.eligible, 'null estimate is ineligible');
  requireThat(e.denominator === null || e.denominator > 0, 'estimate denominator must be positive');
}
function checkValue(d: MetricDescriptor, v: number): void {
  requireThat(d.minimum === null || v >= d.minimum, 'metric value below minimum');
  requireThat(d.maximum === null || v <= d.maximum, 'metric value above maximum');
  requireThat(d.value_kind !== 'binary' || v === 0 || v === 1, 'binary value must be zero or one');
  requireThat(d.value_kind !== 'count' || (v >= 0 && Number.isInteger(v)), 'count value must be a nonnegative integer');
}
function checkObservation(o: ResultObservation): void {
  requireThat(o.observation_id === logicalObservationId(o.identity), 'observation_id does not match logical identity');
  requireThat(o.previous_attempt_id !== o.attempt_id, 'attempt cannot retry itself');
  if (o.outcome === 'observed') {
    requireThat(o.value !== null && o.execution === 'completed' && o.reason === null, 'observed requires completed execution, value, and no reason');
  } else {
    requireThat(o.reason !== null, 'non-observed outcome requires reason');
    requireThat(o.outcome === 'model_timeout' || o.value === null, 'unmeasured outcome must have null value');
  }
  const expected: Partial<Record<ResultOutcome, ResultExecution>> = { infrastructure_error: 'failed', cancelled: 'cancelled', not_attempted: 'not_attempted', legacy_unknown: 'unknown', grader_failed: 'completed' };
  requireThat(expected[o.outcome] === undefined || o.execution === expected[o.outcome], 'execution contradicts measurement outcome');
  o.artifacts.forEach(checkArtifact);
  if (o.judge?.calibration) checkArtifact(o.judge.calibration);
}
function checkBenchmark(b: BenchmarkResultV2): void {
  checkEligibility(b.eligibility);
  checkEstimate(b.primary_estimate);
  b.artifacts.forEach(checkArtifact);
  const c = b.coverage;
  requireThat(c.terminal === c.completed + c.failed + c.cancelled, 'terminal = completed + failed + cancelled');
  requireThat(c.requested === c.terminal + c.not_attempted + c.unknown, 'requested = terminal + not_attempted + unknown');
  requireThat(c.attempted === c.terminal, 'terminal envelope attempted = terminal');
  const selected = new Set(b.selection.map(selectionKey));
  requireThat(selected.size === b.selection.length && selected.size === c.requested, 'selection must be unique and match requested count');
  for (const m of Object.values(b.metrics)) {
    checkEstimate(m.estimate);
    const d = m.descriptor;
    requireThat(d.minimum === null || d.maximum === null || d.minimum <= d.maximum, 'metric minimum exceeds maximum');
    if (d.timeout_value !== null) checkValue(d, d.timeout_value);
  }
  const attempts = new Map<string, ResultObservation>();
  const accepted = new Map<string, ResultObservation>();
  const executions = new Map<string, ResultExecution>();
  for (const o of b.observations) {
    checkObservation(o);
    const key = selectionKey(o.identity);
    const mid = o.identity.metric_id;
    requireThat(selected.has(key) && o.identity.benchmark_id === b.benchmark_id, 'observation outside selected benchmark manifest');
    requireThat(Object.hasOwn(b.metrics, mid), 'observation metric is undeclared');
    const attemptKey = JSON.stringify([o.observation_id, o.attempt_id]);
    requireThat(!attempts.has(attemptKey), 'duplicate observation attempt');
    if (o.previous_attempt_id !== null) {
      const previous = attempts.get(JSON.stringify([o.observation_id, o.previous_attempt_id]));
      requireThat(previous !== undefined && !previous.accepted, 'retry predecessor must precede retry and be superseded');
    }
    attempts.set(attemptKey, o);
    const d = b.metrics[mid]!.descriptor;
    if (o.value !== null) checkValue(d, o.value);
    requireThat(o.outcome !== 'model_timeout' || o.value === d.timeout_value, 'timeout value must follow declared metric policy');
    if (o.accepted) {
      const acceptedKey = JSON.stringify([key, mid]);
      requireThat(!accepted.has(acceptedKey), 'multiple accepted attempts for one logical observation');
      accepted.set(acceptedKey, o);
      requireThat(!executions.has(key) || executions.get(key) === o.execution, 'metrics disagree about sample execution');
      executions.set(key, o.execution);
    }
  }
  requireThat(accepted.size === selected.size * Object.keys(b.metrics).length, 'every selected unit requires one accepted outcome per metric');
  requireThat(selected.size === 0 || Object.keys(b.metrics).length > 0, 'selected observations require declared metrics');
  for (const status of ['completed', 'failed', 'cancelled', 'not_attempted', 'unknown'] as const) {
    requireThat(c[status] === [...executions.values()].filter(v => v === status).length, 'coverage differs from accepted observations');
  }
  for (const [mid, m] of Object.entries(b.metrics)) {
    requireThat(m.descriptor.metric_id === mid, 'metric map key differs from descriptor identity');
    const rows = [...accepted.values()].filter(o => o.identity.metric_id === mid);
    let total = 0;
    for (const [outcomeName, n] of Object.entries(m.outcome_counts)) {
      requireThat(n === rows.filter(o => o.outcome === outcomeName).length, 'metric outcome counts differ from accepted observations');
      total += n;
    }
    requireThat(total === rows.length, 'metric outcome counts must account for every accepted observation');
    requireThat(m.scored === rows.filter(o => o.value !== null).length, 'metric scored count differs from measured observations');
    requireThat(m.scored !== 0 || m.estimate.value === null, 'all-unscored metric cannot have an estimate');
    if (m.estimate.value !== null) {
      requireThat(m.descriptor.minimum === null || m.estimate.value >= m.descriptor.minimum, 'estimate below metric minimum');
      requireThat(m.descriptor.maximum === null || m.estimate.value <= m.descriptor.maximum, 'estimate above metric maximum');
    }
  }
  const primary = b.primary_metric_id !== null && Object.hasOwn(b.metrics, b.primary_metric_id) ? b.metrics[b.primary_metric_id] : undefined;
  if (primary === undefined) requireThat(b.primary_estimate.value === null && !b.eligibility.eligible, 'missing primary metric cannot yield eligible estimate');
  else requireThat(isDeepStrictEqual(b.primary_estimate, primary.estimate), 'primary estimate differs from declared metric');
  requireThat(b.execution !== 'completed' || c.terminal === c.requested, 'completed benchmark requires terminal records for every selected unit');
  requireThat(!b.eligibility.eligible || (b.execution === 'completed' && c.completed === c.requested && b.primary_estimate.eligibility.eligible), 'eligible benchmark requires completed samples and eligible primary');
}

/** Validate both structure and cross-record invariants; never coerce primitive values. */
export function validateResult(value: unknown): asserts value is ResultEnvelope {
  envelope(value, 'result');
  const r = value as ResultEnvelope;
  checkEligibility(r.eligibility);
  checkEstimate(r.overall_estimate);
  r.artifacts.forEach(checkArtifact);
  const ids = r.benchmarks.map(b => b.benchmark_id);
  requireThat(new Set(ids).size === ids.length, 'benchmark identities must be unique');
  for (const b of r.benchmarks) {
    checkBenchmark(b);
    for (const o of b.observations) requireThat(o.identity.run_id === r.run_id && o.identity.model_id === r.model_id, 'observation run/model differs from envelope');
  }
  requireThat(r.aggregation_id !== null || r.overall_estimate.value === null, 'overall estimate requires declared aggregation');
  requireThat(r.execution !== 'completed' || r.benchmarks.every(b => b.execution === 'completed'), 'completed envelope requires completed benchmarks');
  requireThat(!r.eligibility.eligible || (r.execution === 'completed' && r.benchmarks.length > 0 && r.benchmarks.every(b => b.eligibility.eligible)), 'eligible envelope requires completed eligible benchmarks');
}
export function readResult(payload: string): ResultEnvelope {
  const result: unknown = JSON.parse(payload);
  validateResult(result);
  return result;
}
export function writeResult(result: ResultEnvelope): string {
  validateResult(result);
  return JSON.stringify(result);
}
