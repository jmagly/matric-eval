/** Strict migration ingress. Legacy imports are evidence, never inferred observations. */
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { requireComparable, validateSuiteAggregation, validateResult, type SuiteAggregation, type ResultEnvelope, type ResultEligibility, type ArtifactReference } from './result-contract.js';
import { validateTrials, type TrialEvaluation } from './trials.js';

export class ConsumerError extends TypeError {}
const sha = (source: string): string => createHash('sha256').update(source, 'utf8').digest('hex');
export function strictJson(source: string): unknown {
  let at = 0;
  const fail = (reason = 'nonfinite_or_invalid_json'): never => { throw new ConsumerError(reason); };
  const whitespace = (): void => { while (/[\x20\t\r\n]/u.test(source[at] ?? '\0')) at++; };
  const string = (): string => {
    const start = at++;
    while (at < source.length) {
      const character = source[at++];
      if (character === '\\') { at++; continue; }
      if (character === '"') {
        let decoded: unknown;
        try { decoded = JSON.parse(source.slice(start, at)); } catch { return fail(); }
        if (typeof decoded !== 'string') return fail();
        for (let i = 0; i < decoded.length; i++) {
          const unit = decoded.charCodeAt(i);
          if (unit >= 0xd800 && unit <= 0xdbff) {
            const next = decoded.charCodeAt(++i);
            if (!(next >= 0xdc00 && next <= 0xdfff)) return fail();
          } else if (unit >= 0xdc00 && unit <= 0xdfff) return fail();
        }
        return decoded;
      }
    }
    return fail();
  };
  const value = (depth: number): void => {
    if (depth > 256) fail();
    whitespace();
    const first = source[at];
    if (first === '"') { string(); return; }
    if (first === '{') {
      at++; whitespace(); const keys = new Set<string>();
      if (source[at] === '}') { at++; return; }
      while (true) {
        whitespace(); if (source[at] !== '"') fail();
        const key = string(); if (keys.has(key)) fail('duplicate_object_key'); keys.add(key);
        whitespace(); if (source[at++] !== ':') fail(); value(depth + 1); whitespace();
        if (source[at] === '}') { at++; return; }
        if (source[at++] !== ',') fail();
      }
    }
    if (first === '[') {
      at++; whitespace(); if (source[at] === ']') { at++; return; }
      while (true) {
        value(depth + 1); whitespace(); if (source[at] === ']') { at++; return; }
        if (source[at++] !== ',') fail();
      }
    }
    for (const literal of ['true', 'false', 'null']) if (source.startsWith(literal, at)) { at += literal.length; return; }
    const number = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/u.exec(source.slice(at));
    if (!number || !Number.isFinite(Number(number[0]))) fail();
    at += number![0].length;
  };
  value(0); whitespace(); if (at !== source.length) fail();
  try { return JSON.parse(source); } catch { return fail(); }
}

export interface LegacyImport {
  consumer_import_schema_version: '1'; conversion_profile: 'legacy-preservation/1';
  source_format: 'legacy_model/1' | 'legacy_summary/1' | 'legacy_matrix/1'; source_sha256: string; conversion_sha256: string;
  source_text: string; payload: Record<string, unknown>; status: 'legacy_unverified'; eligibility: ResultEligibility;
}
export interface ConsumerFailure { run_id: string; model_id: string; execution: 'failed' | 'cancelled' | 'unknown'; reason: 'result_projection_unavailable'; artifacts: ArtifactReference[]; eligibility: ResultEligibility }
export interface ResultCollection { result_collection_schema_version: '1'; results: ResultEnvelope[]; failures: ConsumerFailure[] }
export type ConsumerResult = ResultEnvelope | TrialEvaluation | LegacyImport | ResultCollection;
export type VersionedEvaluation = ResultEnvelope | ResultCollection;
const markers = ['result_schema_version', 'trial_schema_version', 'consumer_import_schema_version', 'result_collection_schema_version'];
function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new ConsumerError('unrecognized_legacy_shape');
  return value as Record<string, unknown>;
}
function exact(row: Record<string, unknown>, names: string[]): void {
  if (Object.keys(row).length !== names.length || names.some(key => !Object.hasOwn(row, key))) throw new ConsumerError('invalid_versioned_result');
}
function legacyFormat(value: unknown): LegacyImport['source_format'] {
  const row = object(value);
  if (row['schema_version'] === '1' || row['schema_version'] === '2') {
    if (!Object.keys(row).some(key => key === 'version' || key.endsWith('_schema_version') && key !== 'schema_version') && !markers.some(key => Object.hasOwn(row, key)) && Array.isArray(row['results']) && Number.isInteger(row['matrix_runs']) && row['matrix_runs'] === row['results'].length && typeof row['timestamp'] === 'string' && typeof row['tier'] === 'string' && row['results'].every(item => legacyFormat(item) === 'legacy_model/1')) return 'legacy_matrix/1';
    throw new ConsumerError('unrecognized_legacy_shape');
  }
  if (Object.keys(row).some(key => key === "version" || key === "schema_version" || key.endsWith("_schema_version"))) throw new ConsumerError("unsupported_schema");
  if (markers.some(key => Object.hasOwn(row, key))) throw new ConsumerError('unrecognized_legacy_shape');
  if (typeof row['model'] === 'string' && /\S/u.test(row['model']) && ((row['benchmarks'] !== null && typeof row['benchmarks'] === 'object' && !Array.isArray(row['benchmarks'])) || (typeof row['status'] === 'string' && ['error', 'failed'].includes(row['status']) && typeof row['error'] === 'string'))) {
    if (Object.hasOwn(row, 'results')) throw new ConsumerError('ambiguous_schema');
    return 'legacy_model/1';
  }
  if (Array.isArray(row['results']) && row['results'].every(item => legacyFormat(item) === 'legacy_model/1')) return 'legacy_summary/1';
  throw new ConsumerError('unrecognized_legacy_shape');
}
export function readConsumerResult(source: string): ConsumerResult {
  const row = object(strictJson(source)); const present = markers.filter(key => Object.hasOwn(row, key));
  if (present.length > 1) throw new ConsumerError('ambiguous_schema');
  if (present.length === 0) return {
    consumer_import_schema_version: '1', conversion_profile: 'legacy-preservation/1', source_format: legacyFormat(row),
    source_sha256: sha(source), conversion_sha256: sha('legacy-preservation/1\0' + source), source_text: source, payload: row,
    status: 'legacy_unverified', eligibility: { eligible: false, reasons: ['legacy_unverified'] },
  };
  const marker = present[0]!;
  if (row[marker] !== (marker === 'result_schema_version' ? '2' : '1')) throw new ConsumerError('unsupported_schema');
  try {
    if (marker === 'result_schema_version') {
      const comparison = row['comparability'];
      if (comparison && typeof comparison === 'object' && 'payload' in comparison && typeof comparison.payload === 'string') strictJson(comparison.payload);
      validateResult(row); return row;
    }
    if (marker === 'trial_schema_version') { validateTrials(row); return row; }
    if (marker === 'consumer_import_schema_version') {
      exact(row, ['consumer_import_schema_version', 'conversion_profile', 'source_format', 'source_sha256', 'conversion_sha256', 'source_text', 'payload', 'status', 'eligibility']);
      if (typeof row['source_text'] !== 'string') throw new ConsumerError();
      const parsed = readConsumerResult(row['source_text']);
      if (!('consumer_import_schema_version' in parsed) || !isDeepStrictEqual(parsed, row)) throw new ConsumerError();
      return parsed;
    }
    exact(row, ['result_collection_schema_version', 'results', 'failures']);
    if (!Array.isArray(row['results']) || !Array.isArray(row['failures']) || row['results'].length + row['failures'].length === 0) throw new ConsumerError();
    const keys = new Set<string>();
    for (const result of row['results']) {
      const parsed = readConsumerResult(JSON.stringify(result));
      if (!('result_schema_version' in parsed)) throw new ConsumerError();
      const key = JSON.stringify([parsed.run_id, parsed.model_id]); if (keys.has(key)) throw new ConsumerError(); keys.add(key);
    }
    for (const item of row['failures']) {
      const failure = object(item); exact(failure, ['run_id', 'model_id', 'execution', 'reason', 'artifacts', 'eligibility']);
      if (typeof failure['run_id'] !== 'string' || !/\S/u.test(failure['run_id'])) throw new ConsumerError();
      const key = JSON.stringify([failure['run_id'], failure['model_id']]); if (keys.has(key)) throw new ConsumerError(); keys.add(key);
      if (typeof failure['model_id'] !== 'string' || !/\S/u.test(failure['model_id']) || (typeof failure['execution'] !== 'string' || !['failed', 'cancelled', 'unknown'].includes(failure['execution'])) || failure['reason'] !== 'result_projection_unavailable' || !isDeepStrictEqual(failure['eligibility'], {eligible: false, reasons: ['result_projection_unavailable']}) || !Array.isArray(failure['artifacts'])) throw new ConsumerError();
      for (const reference of failure['artifacts']) {
        const artifact = object(reference); exact(artifact, ['uri', 'sha256', 'unavailable_reason']);
        if (typeof artifact['uri'] !== 'string' || !/\S/u.test(artifact['uri']) || !(artifact['sha256'] === null ? typeof artifact['unavailable_reason'] === 'string' && /\S/u.test(artifact['unavailable_reason']) : typeof artifact['sha256'] === 'string' && /^[a-f0-9]{64}$/u.test(artifact['sha256']) && artifact['unavailable_reason'] === null)) throw new ConsumerError();
      }
    }
    return row as unknown as ResultCollection;
  } catch { throw new ConsumerError('invalid_versioned_result'); }
}
export function writeConsumerResult(result: ConsumerResult): string {
  const serialized = JSON.stringify(result, (_key, value: unknown) => {
    if (typeof value === 'number' && !Number.isFinite(value) || value === undefined) throw new ConsumerError('nonfinite_or_invalid_json');
    return value;
  });
  readConsumerResult(serialized); return serialized;
}
export function projectLegacy(result: ConsumerResult): Record<string, unknown> {
  result = readConsumerResult(writeConsumerResult(result));
  if (!('consumer_import_schema_version' in result)) throw new ConsumerError('legacy_projection_unrepresentable:versioned_measurements');
  const rows = result.source_format !== 'legacy_model/1' ? result.payload['results'] as unknown[] : [result.payload];
  const statuses = rows.map(value => object(value)['status']);
  const counts: Record<string, number> = {total_models: rows.length, models_evaluated: rows.length, successful: statuses.filter(value => value === 'success').length, failed: statuses.filter(value => value === 'failed' || value === 'error').length, skipped: statuses.filter(value => value === 'skipped').length};
  for (const [key, expected] of Object.entries(counts)) if (Object.hasOwn(result.payload, key) && (!Number.isSafeInteger(result.payload[key]) || result.payload[key] !== expected)) throw new ConsumerError('legacy_projection_unrepresentable:counts');
  for (const value of [result.payload, ...rows]) {
    const row = object(value);
    for (const key of ["size_gb", "duration_seconds"]) if (Object.hasOwn(row, key) && row[key] !== null && (typeof row[key] !== "number" || (row[key] as number) < 0)) throw new ConsumerError("legacy_projection_unrepresentable:metadata");
    for (const key of ["timestamp", "output_dir", "error"]) if (Object.hasOwn(row, key) && row[key] !== null && typeof row[key] !== "string") throw new ConsumerError("legacy_projection_unrepresentable:metadata");
  }
  for (const value of rows) {
    const row = object(value);
    if (typeof row['tier'] !== 'string' || !['smoke', 'quick', 'full'].includes(row['tier']) || typeof row['status'] !== 'string' || !['success', 'error', 'failed', 'skipped'].includes(row['status'])) throw new ConsumerError('legacy_projection_unrepresentable:status_or_tier');
    if (typeof row['overall_score'] !== 'number' || !Number.isFinite(row['overall_score']) || row['eligible'] === false || ['observation_result', 'comparability', 'trials', 'eligibility'].some(key => Object.hasOwn(row, key))) throw new ConsumerError('legacy_projection_unrepresentable:overall_score_or_eligibility');
    for (const value of Object.values(object(row['benchmarks']))) {
      const benchmark = object(value);
      if (typeof benchmark['score'] !== 'number' || !Number.isFinite(benchmark['score']) || benchmark['eligible'] === false || ['observation_result', 'metrics', 'trials', 'eligibility'].some(key => Object.hasOwn(benchmark, key))) throw new ConsumerError('legacy_projection_unrepresentable:benchmark_measurements');
    }
  }
  return result.payload;
}

export interface RecommendationReportV2 {
  recommendation_schema_version: '2'; status: 'recommended' | 'no_recommendation';
  recommendations: Record<string, {status: 'recommended' | 'no_recommendation'; recommended: string | null; score: number | null; alternatives: {model: string; score: number}[]; units: string; direction: 'higher' | 'lower'; reasons: string[]}>;
  model_scores: Record<string, {model: string; run_id: string; benchmark_scores: Record<string, number | null>; capability_scores: Record<string, number | null>; overall_score: number | null; size_gb: number | null}>;
  best_overall: null; best_balanced: null; exclusions: Record<string, unknown>[];
  sources: ConsumerResult[]; policy: Record<string, unknown> | null; judge_controls: Record<string, unknown>[]; limitations: string[];
}
function closeNumber(actual: unknown, expected: number | null): boolean {
  return expected === null ? actual === null : typeof actual === 'number' && Number.isFinite(actual) && Math.abs(actual - expected) <= 1e-12 * Math.max(1, Math.abs(expected));
}
function orderedText(a: string, b: string): number {
  const aa = Array.from(a, c => c.codePointAt(0)!); const bb = Array.from(b, c => c.codePointAt(0)!);
  for (let i = 0; i < Math.min(aa.length, bb.length); i++) if (aa[i] !== bb[i]) return aa[i]! - bb[i]!;
  return aa.length - bb.length;
}
function capabilityValue(source: ResultEnvelope, declaration: SuiteAggregation): number | null {
  if (source.benchmarks.length !== declaration.terms.length) return null;
  const values: number[] = []; const weights: number[] = [];
  for (const term of [...declaration.terms].sort((a,b) => orderedText(a.benchmark_id,b.benchmark_id))) {
    const benchmark = source.benchmarks.find(item => item.benchmark_id === term.benchmark_id);
    const metric = benchmark?.metrics[term.metric_id]; const t = term.transform;
    if (!benchmark || benchmark.primary_metric_id !== term.metric_id || !metric || !benchmark.eligibility.eligible || benchmark.execution !== 'completed' || benchmark.coverage.completed !== benchmark.coverage.requested || !metric.estimate.eligibility.eligible || metric.estimate.value === null) return null;
    const d = metric.descriptor; const value = metric.estimate.value;
    if (d.units !== t.source_units || d.minimum !== t.source_minimum || d.maximum !== t.source_maximum || d.direction !== t.source_direction || d.minimum !== null && value < d.minimum || d.maximum !== null && value > d.maximum) return null;
    const transformed = value * t.scale + t.offset;
    if (!Number.isFinite(transformed)) return null;
    values.push(transformed * term.weight); weights.push(term.weight);
  }
  // Compensated sum mirrors Python fsum within the reader's explicit 1e-12 tolerance.
  const sum = (terms: number[]): number => { let total = 0; let correction = 0; for (const value of terms) { const next = total + value; correction += Math.abs(total) >= Math.abs(value) ? (total-next)+value : (value-next)+total; total = next; } return total + correction; };
  const numerator = sum(values); const denominator = sum(weights); const value = numerator / denominator;
  return [numerator, denominator, value].every(Number.isFinite) ? value : null;
}
export function readRecommendationReport(source: string): RecommendationReportV2 {
  const row = object(strictJson(source));
  const nullableNumber = (value: unknown): boolean => value === null || typeof value === 'number' && Number.isFinite(value);
  const strings = (value: unknown): boolean => Array.isArray(value) && value.every(item => typeof item === 'string');
  try {
    exact(row, ['recommendation_schema_version', 'status', 'recommendations', 'model_scores', 'best_overall', 'best_balanced', 'exclusions', 'sources', 'policy', 'judge_controls', 'limitations']);
    if (row['recommendation_schema_version'] !== '2' || (typeof row['status'] !== 'string' || !['recommended', 'no_recommendation'].includes(row['status'])) || row['best_overall'] !== null || row['best_balanced'] !== null || !Array.isArray(row['sources']) || !Array.isArray(row['exclusions']) || !Array.isArray(row['judge_controls']) || !strings(row['limitations'])) throw new ConsumerError();
    let sources: ResultEnvelope[] = [];
    for (const item of row['sources']) {
      const parsed = readConsumerResult(JSON.stringify(item));
      if ('result_schema_version' in parsed) sources.push(parsed);
      if ('result_collection_schema_version' in parsed) sources.push(...parsed.results);
    }
    const identities = new Map<string, ResultEnvelope>();
    for (const source of sources) { const key = JSON.stringify([source.run_id, source.model_id]); const previous = identities.get(key); if (previous && !isDeepStrictEqual(previous, source)) throw new ConsumerError(); identities.set(key, source); }
    sources = [...identities.values()];
    for (const item of row['exclusions']) {
      const exclusion = object(item);
      if (!strings(exclusion['reasons']) || !(exclusion['reasons'] as string[]).length || Object.keys(exclusion).some(key => !['reasons','run_id','model_id','source_index','capability'].includes(key))) throw new ConsumerError();
      for (const key of ['run_id','model_id','capability']) if (Object.hasOwn(exclusion,key) && (typeof exclusion[key] !== 'string' || !/\S/u.test(exclusion[key] as string))) throw new ConsumerError();
      if (Object.hasOwn(exclusion,'source_index') && (!Number.isSafeInteger(exclusion['source_index']) || (exclusion['source_index'] as number) < 0 || (exclusion['source_index'] as number) >= row['sources'].length)) throw new ConsumerError();
    }
    const controls = sources.flatMap(source => source.benchmarks.flatMap(benchmark => benchmark.observations.filter(observation => observation.judge !== null).map(observation => ({run_id:source.run_id,model_id:source.model_id,judge:observation.judge,qualification:'unverified',reason:'qualification_policy_evidence_unavailable'}))));
    if (!isDeepStrictEqual(row['judge_controls'], controls)) throw new ConsumerError();

    const policy = row['policy'] === null ? null : object(row['policy']);
    if (policy !== null) {
      exact(policy, ['version', 'comparison_sha256', 'capabilities', 'minimum_score', 'require_qualified_judges']);
      if (policy['version'] !== '1' || typeof policy['comparison_sha256'] !== 'string' || !/^[a-f0-9]{64}$/u.test(policy['comparison_sha256']) || !nullableNumber(policy['minimum_score']) || typeof policy['require_qualified_judges'] !== 'boolean') throw new ConsumerError();
      const declarations = Object.values(object(policy['capabilities']));
      if (!declarations.length) throw new ConsumerError();
      for (const declaration of declarations) { validateSuiteAggregation(declaration); if (declaration.missingness_policy !== 'require-complete') throw new ConsumerError(); }
      if (policy['minimum_score'] !== null && (new Set((declarations as SuiteAggregation[]).map(item => item.target_units)).size !== 1 || (declarations as SuiteAggregation[]).some(item => item.target_direction !== 'higher'))) throw new ConsumerError();
    }
    const eligible = sources.filter(source => {
      if (!policy || source.comparability?.sha256 !== policy['comparison_sha256'] || policy['require_qualified_judges'] && source.benchmarks.some(b => b.observations.some(o => o.judge !== null))) return false;
      try { requireComparable(source, source); return true; } catch { return false; }
    });
    const candidates = eligible.filter(source => eligible.filter(other => other.model_id === source.model_id).length === 1);
    if (!isDeepStrictEqual(Object.keys(object(row['model_scores'])).sort(), candidates.map(source => source.model_id).sort())) throw new ConsumerError();
    if (!isDeepStrictEqual(Object.keys(object(row['recommendations'])).sort(), Object.keys(policy ? object(policy['capabilities']) : {}).sort())) throw new ConsumerError();
    for (const [name, item] of Object.entries(object(row['model_scores']))) {
      const score = object(item); exact(score, ['model', 'run_id', 'benchmark_scores', 'capability_scores', 'overall_score', 'size_gb']);
      if (score['model'] !== name || typeof score['run_id'] !== 'string' || !nullableNumber(score['overall_score']) || !nullableNumber(score['size_gb'])) throw new ConsumerError();
      const matches = sources.filter(source => source.model_id === name && source.run_id === score['run_id']);
      if (matches.length !== 1 || policy === null) throw new ConsumerError();
      const source = matches[0]!; requireComparable(source, source);
      if (source.comparability?.sha256 !== policy['comparison_sha256'] || score['overall_score'] !== source.overall_estimate.value || score['size_gb'] !== null) throw new ConsumerError();
      if (policy['require_qualified_judges'] && source.benchmarks.some(benchmark => benchmark.observations.some(observation => observation.judge !== null))) throw new ConsumerError();
      if (!isDeepStrictEqual(score['benchmark_scores'], Object.fromEntries(source.benchmarks.map(benchmark => [benchmark.benchmark_id, benchmark.primary_estimate.value])))) throw new ConsumerError();
      if (!isDeepStrictEqual(Object.keys(object(score['capability_scores'])).sort(), Object.keys(object(policy['capabilities'])).sort())) throw new ConsumerError();
      for (const [capability, value] of Object.entries(object(score['capability_scores']))) {
        const declaration = object(policy['capabilities'])[capability]; validateSuiteAggregation(declaration);
        if (!closeNumber(value, capabilityValue(source, declaration))) throw new ConsumerError();
      }
      for (const values of [score['benchmark_scores'], score['capability_scores']]) if (!Object.values(object(values)).every(nullableNumber)) throw new ConsumerError();
    }
    for (const [capability, item] of Object.entries(object(row['recommendations']))) {
      const rec = object(item); exact(rec, ['status', 'recommended', 'score', 'alternatives', 'units', 'direction', 'reasons']);
      if (!nullableNumber(rec['score']) || typeof rec['units'] !== 'string' || (typeof rec['direction'] !== 'string' || !['higher', 'lower'].includes(rec['direction'])) || !strings(rec['reasons']) || !Array.isArray(rec['alternatives'])) throw new ConsumerError();
      if (policy === null) throw new ConsumerError();
      const declaration = object(policy['capabilities'])[capability]; validateSuiteAggregation(declaration);
      if (rec['units'] !== declaration.target_units || rec['direction'] !== declaration.target_direction) throw new ConsumerError();
      const ranking = candidates.map(source => ({model:source.model_id, score:capabilityValue(source, declaration)})).filter((item): item is {model:string;score:number} => item.score !== null && (policy['minimum_score'] === null || item.score >= (policy['minimum_score'] as number))).sort((a,b) => (declaration.target_direction === 'higher' ? b.score-a.score : a.score-b.score) || orderedText(a.model,b.model));
      if (rec['recommended'] !== (ranking[0]?.model ?? null) || !closeNumber(rec['score'], ranking[0]?.score ?? null) || rec['alternatives'].length !== Math.max(0, ranking.length-1)) throw new ConsumerError();
      for (let index=0; index < rec['alternatives'].length; index++) { const alternative=object(rec['alternatives'][index]); if (alternative['model'] !== ranking[index+1]!.model || !closeNumber(alternative['score'], ranking[index+1]!.score)) throw new ConsumerError(); }

      if (rec['status'] === 'recommended') {
        if (typeof rec['recommended'] !== 'string' || typeof rec['score'] !== 'number' || (rec['reasons'] as unknown[]).length || !Object.hasOwn(object(row['model_scores']), rec['recommended'])) throw new ConsumerError();
        if (object(object(object(row['model_scores'])[rec['recommended'] as string])['capability_scores'])[capability] !== rec['score']) throw new ConsumerError();
      } else if (rec['status'] !== 'no_recommendation' || rec['recommended'] !== null || rec['score'] !== null || !(rec['reasons'] as unknown[]).length) throw new ConsumerError();
      for (const candidate of rec['alternatives']) { const alt = object(candidate); exact(alt, ['model', 'score']); if (typeof alt['model'] !== 'string' || typeof alt['score'] !== 'number' || !Number.isFinite(alt['score']) || object(object(object(row['model_scores'])[alt['model']])['capability_scores'])[capability] !== alt['score']) throw new ConsumerError(); }
    }
    if ((row['status'] === 'recommended') !== Object.values(object(row['recommendations'])).some(item => object(item)['status'] === 'recommended')) throw new ConsumerError();
    return row as unknown as RecommendationReportV2;
  } catch { throw new ConsumerError('invalid_recommendation_report'); }
}
