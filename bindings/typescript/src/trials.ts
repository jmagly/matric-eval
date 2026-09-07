/** Strict readers for aligned repeated trials. Native grades and missingness remain explicit. */
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { PARTITION_ROLES, validateResult } from './result-contract.js';
import type { BenchmarkResultV2, ResultEligibility, ResultEstimate, ResultSelection, MetricDescriptor, ArtifactReference } from './result-contract.js';

type Check = (value: unknown, path: string) => void;
function requireThat(condition: boolean, message: string): asserts condition {
  if (!condition) throw new TypeError(message);
}
const text: Check = (v, p) => requireThat(typeof v === 'string' && /\S/u.test(v), `${p} must be nonempty text`);
const finite: Check = (v, p) => requireThat(typeof v === 'number' && Number.isFinite(v), `${p} must be finite`);
const count: Check = (v, p) => requireThat(typeof v === 'number' && Number.isSafeInteger(v) && v >= 0, `${p} must be a nonnegative safe integer`);
const boolean: Check = (v, p) => requireThat(typeof v === 'boolean', `${p} must be boolean`);
const nullable = (check: Check): Check => (v, p) => { if (v !== null) check(v, p); };
const enumeration = (values: readonly string[]): Check => (v, p) => requireThat(typeof v === 'string' && values.includes(v), `${p} has an unsupported value`);
const array = (check: Check): Check => (v, p) => {
  requireThat(Array.isArray(v), `${p} must be an array`);
  for (let i = 0; i < v.length; i++) check(v[i], `${p}[${i}]`);
};
const object = (fields: Record<string, Check>, optional: Record<string, Check> = {}): Check => (v, p) => {
  requireThat(v !== null && typeof v === 'object' && !Array.isArray(v), `${p} must be an object`);
  const row = v as Record<string, unknown>;
  requireThat(Object.keys(row).every(k => Object.hasOwn(fields, k) || Object.hasOwn(optional, k)), `${p} has missing or unknown fields`);
  for (const [key, check] of Object.entries(fields)) {
    requireThat(Object.hasOwn(row, key), `${p}.${key} is required`);
    check(row[key], `${p}.${key}`);
  }
  for (const [key, check] of Object.entries(optional)) if (Object.hasOwn(row, key)) check(row[key], `${p}.${key}`);
};
const eligibility = object({ eligible: boolean, reasons: array(text) });

export interface PassPredicate { version: '1'; kind: 'equals' | 'at_least'; threshold: number; units: string }
export interface TrialProtocol {
  version: '1'; task_content_sha256: string; n: number; k: number; metric_id: string; metric_version: string; predicate: PassPredicate;
  generation_seeds: number[]; root_generation_seed: number; selection_seed: number;
  independence: 'unverified'; statistical_claim?: 'descriptive_only';
}
export interface GenerationEvidence {
  requested_seed: number; recorded_seed: number | null; temperature: number | null; provider_id: string;
  forwarding: 'recorded' | 'unverified'; honored: 'unverified'; limitations: string[];
}
export interface TrialRecord {
  trial_id: string; generation_seed: number; benchmark: BenchmarkResultV2 | null; unavailable_reason: string | null;
  artifacts?: ArtifactReference[]; failure_code?: string | null;
  native_trial_id?: string; generation_evidence?: GenerationEvidence | null;
}
export interface PerTaskResult {
  allocation_id: string; sample_id: string; n_requested: number; n_observed: number; c: number;
  pass_at_k: ResultEstimate; all_n_success: ResultEstimate;
}
export interface TrialEvaluation {
  trial_schema_version: '1'; run_id: string; model_id: string; benchmark_id: string; protocol: TrialProtocol;
  manifest: ResultSelection[]; manifest_sha256: string; trials: TrialRecord[]; per_task: PerTaskResult[];
  macro_pass_at_k: ResultEstimate; macro_all_n_success: ResultEstimate;
  execution: 'completed' | 'partial' | 'failed'; eligibility: ResultEligibility; limitations: string[];
}

const positive: Check = (v, p) => { count(v, p); requireThat((v as number) > 0, `${p} must be positive`); };
const digest: Check = (v, p) => requireThat(typeof v === 'string' && /^[a-f0-9]{64}$/u.test(v), `${p} must be a SHA-256 digest`);
const artifact = object({ uri: text, sha256: nullable(digest), unavailable_reason: nullable(text) });
const predicate = object({ version: enumeration(['1']), kind: enumeration(['equals', 'at_least']), threshold: finite, units: text });
const protocol = object({ version: enumeration(['1']), task_content_sha256: digest, n: positive, k: positive, metric_id: text, metric_version: text,
  predicate, generation_seeds: array(count), root_generation_seed: count, selection_seed: count, independence: enumeration(['unverified']) },
  { statistical_claim: enumeration(['descriptive_only']) });
const generationEvidence = object({ requested_seed: count, recorded_seed: nullable(count), temperature: nullable(finite),
  provider_id: text, forwarding: enumeration(['recorded', 'unverified']), honored: enumeration(['unverified']), limitations: array(text) });
const selection = object({ allocation_id: text, sample_id: text, trial_id: text,
  data: object({ partition_schema_version: enumeration(['1']), role: enumeration(PARTITION_ROLES), row_id: text, source_id: text, independent_unit_id: text }) });
const estimate = object({ value: nullable(finite), reason: nullable(text), numerator: nullable(finite), denominator: nullable(finite), method: text, eligibility });
const nestedBenchmark: Check = (v, p) => requireThat(v !== null && typeof v === 'object' && !Array.isArray(v), `${p} must be a benchmark object`);
const trial = object({ trial_id: text, generation_seed: count, benchmark: nullable(nestedBenchmark), unavailable_reason: nullable(text) },
  { native_trial_id: text, generation_evidence: nullable(generationEvidence), artifacts: array(artifact), failure_code: nullable(text) });
const perTask = object({ allocation_id: text, sample_id: text, n_requested: positive, n_observed: count, c: count, pass_at_k: estimate, all_n_success: estimate });
const report = object({ trial_schema_version: enumeration(['1']), run_id: text, model_id: text, benchmark_id: text, protocol,
  manifest: array(selection), manifest_sha256: digest, trials: array(trial), per_task: array(perTask), macro_pass_at_k: estimate,
  macro_all_n_success: estimate, execution: enumeration(['completed', 'partial', 'failed']), eligibility, limitations: array(text) });

function compareUnicode(a: string, b: string): number {
  const x = Array.from(a, c => c.codePointAt(0)!);
  const y = Array.from(b, c => c.codePointAt(0)!);
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i]! - y[i]!;
  return x.length - y.length;
}
function sortedObject(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortedObject);
  if (value === null || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).sort(([a], [b]) => compareUnicode(a, b)).map(([k, v]) => [k, sortedObject(v)]));
}
/** Ordered selection references contain strings only, so this matches Python's UTF-8 canonical JSON. */
export function trialManifestDigest(manifest: ResultSelection[]): string {
  array(selection)(manifest, 'manifest');
  return createHash('sha256').update(JSON.stringify(sortedObject(manifest)), 'utf8').digest('hex');
}
function taskKey(s: { allocation_id: string; sample_id: string }): string { return JSON.stringify([s.allocation_id, s.sample_id]); }
function missing(reason: string, method: string): ResultEstimate {
  return { value: null, reason, numerator: null, denominator: null, method, eligibility: { eligible: false, reasons: [reason] } };
}
function measured(value: number, numerator: number | null, denominator: number | null, method: string, reasons: string[]): ResultEstimate {
  return { value, reason: null, numerator, denominator, method, eligibility: { eligible: reasons.length === 0, reasons } };
}
function choose(n: number, k: number): bigint {
  const m = Math.min(k, n - k);
  let result = 1n;
  for (let i = 1; i <= m; i++) result = result * BigInt(n - m + i) / BigInt(i);
  return result;
}
function bigRatio(numerator: bigint, denominator: bigint): number {
  if (numerator === 0n) return 0;
  const numeratorShift = Math.max(0, numerator.toString(2).length - 60);
  const denominatorShift = Math.max(0, denominator.toString(2).length - 60);
  return Number(numerator >> BigInt(numeratorShift)) / Number(denominator >> BigInt(denominatorShift)) * 2 ** (numeratorShift - denominatorShift);
}
function passAtK(n: number, c: number, k: number): number {
  if (n - c < k) return 1;
  const denominator = choose(n, k);
  // Subtract exact integers before division to retain rare successes.
  return bigRatio(denominator - choose(n - c, k), denominator);
}
function sum(values: number[]): number {
  // Neumaier compensation keeps macro sums close to Python's math.fsum.
  let total = 0;
  let compensation = 0;
  for (const value of values) {
    const next = total + value;
    compensation += Math.abs(total) >= Math.abs(value) ? (total - next) + value : (value - next) + total;
    total = next;
  }
  return total + compensation;
}
function checkEstimateMatches(actual: ResultEstimate, expected: ResultEstimate): void {
  for (const key of ['value', 'numerator', 'denominator'] as const) {
    const a = actual[key]; const e = expected[key];
    requireThat(a === e || (a !== null && e !== null && Math.abs(a - e) <= 1e-12 * Math.max(1, Math.abs(e))), `trial estimate ${key} differs from aligned observations`);
  }
  requireThat(actual.reason === expected.reason && actual.method === expected.method && isDeepStrictEqual(actual.eligibility, expected.eligibility), 'trial estimate metadata differs from aligned observations');
}

/** Validate native observations and recompute every derived task and macro result. */
export function validateTrials(value: unknown): asserts value is TrialEvaluation {
  report(value, 'trials');
  const r = value as TrialEvaluation;
  const p = r.protocol;
  requireThat(p.k <= p.n, 'trial protocol requires k <= n');
  requireThat(p.generation_seeds.length === p.n && new Set(p.generation_seeds).size === p.n, 'generation seeds must contain n distinct values');
  requireThat(r.manifest_sha256 === trialManifestDigest(r.manifest), 'trial manifest digest differs from selected task manifest');
  const keys = r.manifest.map(taskKey);
  requireThat(keys.length > 0 && new Set(keys).size === keys.length, 'trial manifest must contain unique nonempty task identities');
  requireThat(new Set(r.manifest.map(s => s.trial_id)).size === 1, 'task manifest must use one selection trial marker');
  requireThat(r.trials.length === p.n && r.trials.every((t, i) => t.trial_id === `trial-${i}`), 'trial records must exactly match ordered protocol trial identities');
  const flags = new Map(keys.map(k => [k, [] as boolean[]]));
  let completed = 0;
  let descriptorBaseline: MetricDescriptor | undefined;
  let benchmarkMeasurementIneligible = false;
  const limitations = ['statistical_independence_unverified', 'descriptive_statistics_only'];
  for (const [index, t] of r.trials.entries()) {
    requireThat(t.generation_seed === p.generation_seeds[index], 'trial generation seed differs from protocol');
    requireThat((t.benchmark === null) === (t.unavailable_reason !== null), 'missing trial benchmark requires an unavailable reason');
    for (const a of t.artifacts ?? []) requireThat((a.sha256 === null) === (a.unavailable_reason !== null), 'artifact needs either digest or unavailable reason');
    const evidence = t.generation_evidence;
    if (evidence == null) limitations.push(`generation_evidence_unavailable:${t.trial_id}`);
    else {
      requireThat(evidence.requested_seed === t.generation_seed, 'generation evidence seed differs from trial');
      requireThat(evidence.forwarding !== 'recorded' || evidence.recorded_seed === evidence.requested_seed, 'recorded forwarding requires matching requested and recorded seeds');
      limitations.push(...evidence.limitations.map(item => `${t.trial_id}:${item}`), `generation_seed_honoring_unverified:${t.trial_id}`);
    }
    const b = t.benchmark;
    if (b === null) continue;
    benchmarkMeasurementIneligible ||= !b.eligibility.eligible;
    validateResult({ result_schema_version: '2', run_id: r.run_id, model_id: r.model_id, created_at: 'trial-validation', provenance_schema_version: '1',
      configuration_sha256: null, execution: b.execution, eligibility: { eligible: false, reasons: ['trial-validation'] },
      benchmarks: [b], aggregation_id: null, overall_estimate: missing('aggregation_undeclared', 'unavailable'), artifacts: [] });
    requireThat(b.benchmark_id === r.benchmark_id, 'trial benchmark identity differs from evaluation');
    requireThat(isDeepStrictEqual(b.selection.map(taskKey), keys), 'trial selected task manifest differs in identity or order');
    for (const [i, s] of b.selection.entries()) {
      requireThat(s.trial_id === t.trial_id, 'inner selection trial identity differs from outer trial');
      requireThat(isDeepStrictEqual(s.data, r.manifest[i]!.data), 'trial data references differ from fixed task manifest');
    }
    if (b.execution === 'completed') completed++;
    for (const row of b.observations) requireThat(row.identity.trial_id === t.trial_id, 'inner observation trial identity differs from outer trial');
    const metric = b.metrics[p.metric_id];
    if (metric === undefined) continue;
    requireThat(metric.observation_metric_id == null, 'trial pass predicate requires a direct observation metric');
    requireThat(metric.descriptor.version === p.metric_version && metric.descriptor.units === p.predicate.units, 'trial metric version or units differ from pass predicate');
    if (descriptorBaseline === undefined) descriptorBaseline = metric.descriptor;
    else requireThat(isDeepStrictEqual(descriptorBaseline, metric.descriptor), 'trial metric descriptor differs across trials');
    for (const row of b.observations) {
      if (!row.accepted || row.identity.metric_id !== p.metric_id || !['observed', 'model_timeout'].includes(row.outcome) || row.value === null) continue;
      flags.get(taskKey(row.identity))!.push(p.predicate.kind === 'equals' ? row.value === p.predicate.threshold : row.value >= p.predicate.threshold);
    }
  }
  const execution = completed === p.n ? 'completed' : r.trials.some(t => t.benchmark?.execution === 'completed' || t.benchmark?.execution === 'partial') ? 'partial' : 'failed';
  const executionReasons = execution === 'completed' ? [] : ['incomplete_trial_execution'];
  if (benchmarkMeasurementIneligible) executionReasons.push('benchmark_measurement_ineligible');
  const tasks: PerTaskResult[] = r.manifest.map(s => {
    const outcomes = flags.get(taskKey(s))!;
    const c = outcomes.filter(Boolean).length;
    const complete = outcomes.length === p.n;
    return { allocation_id: s.allocation_id, sample_id: s.sample_id, n_requested: p.n, n_observed: outcomes.length, c,
      pass_at_k: complete ? measured(passAtK(p.n, c, p.k), null, null, `pass-at-${p.k}/1`, executionReasons) : missing('missing_task_trials', `pass-at-${p.k}/1`),
      all_n_success: complete ? measured(c === p.n ? 1 : 0, null, null, 'all-n-success/1', executionReasons) : missing('missing_task_trials', 'all-n-success/1') };
  });
  requireThat(r.per_task.length === tasks.length, 'trial report per_task differs from aligned observations');
  for (const [i, t] of tasks.entries()) {
    const actual = r.per_task[i]!;
    for (const key of ['allocation_id', 'sample_id', 'n_requested', 'n_observed', 'c'] as const) requireThat(actual[key] === t[key], `trial report task ${key} differs from aligned observations`);
    checkEstimateMatches(actual.pass_at_k, t.pass_at_k);
    checkEstimateMatches(actual.all_n_success, t.all_n_success);
  }
  const incomplete = tasks.some(t => t.n_observed !== p.n);
  const reasons = [...executionReasons, ...(incomplete ? ['missing_task_trials'] : [])];
  const passSum = sum(tasks.map(t => t.pass_at_k.value ?? 0));
  const allSum = sum(tasks.map(t => t.all_n_success.value ?? 0));
  checkEstimateMatches(r.macro_pass_at_k, incomplete ? missing('missing_task_trials', 'task-macro-pass-at-k/1') : measured(passSum / tasks.length, passSum, tasks.length, 'task-macro-pass-at-k/1', reasons));
  checkEstimateMatches(r.macro_all_n_success, incomplete ? missing('missing_task_trials', 'task-macro-all-n-success/1') : measured(allSum / tasks.length, allSum, tasks.length, 'task-macro-all-n-success/1', reasons));
  requireThat(r.execution === execution, 'trial report execution differs from aligned observations');
  requireThat(isDeepStrictEqual(r.eligibility, { eligible: reasons.length === 0, reasons }), 'trial report eligibility differs from aligned observations');
  requireThat(isDeepStrictEqual(r.limitations, [...new Set(limitations)]), 'trial report limitations differ from aligned observations');
}
export function readTrials(payload: string): TrialEvaluation {
  const value: unknown = JSON.parse(payload); validateTrials(value); return value;
}
export function writeTrials(value: TrialEvaluation): string { validateTrials(value); return JSON.stringify(value); }
