import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, mkdtemp, writeFile, rm, access} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readConsumerResult, writeConsumerResult, projectLegacy, strictJson, readRecommendationReport, type VersionedEvaluation} from '../consumer-results.js';
import {createClient} from '../client.js';
import type {EvalOptions, EvalSummary} from '../types.js';

const fixtures = fileURLToPath(new URL('../../../../tests/fixtures/results/consumer/', import.meta.url));
const root = resolve(fixtures, '../../../..');
const read = (name: string) => readFile(join(fixtures, name), 'utf8');
const manifest = JSON.parse(await read('expectations.json')) as {cases: {id:string; source:string; source_sha256:string; kind:string; raw_assertions?: {pointer:string; equals:unknown}[]; metric_ids?:string[]; sample_observation_count?:number; legacy_numeric_projection?:string}[]};
for (const item of manifest.cases) test(`shared consumer fixture ${item.id}`, async () => {
  const source = await read(item.source);
  assert.equal(createHash('sha256').update(source).digest('hex'), item.source_sha256);
  if (item.kind === 'parser_cases') return;
  const result = readConsumerResult(source);
  const raw = 'consumer_import_schema_version' in result ? result.payload : result;
  for (const assertion of item.raw_assertions ?? []) {
    let value: unknown = raw;
    for (const key of assertion.pointer.slice(1).split('/')) value = (value as Record<string, unknown>)[key.replace(/~1/gu, '/').replace(/~0/gu, '~')];
    assert.deepEqual(value, assertion.equals);
  }
  if (item.metric_ids && 'result_schema_version' in result) assert.deepEqual(Object.keys(result.benchmarks[0]!.metrics).sort(), item.metric_ids);
  if (item.sample_observation_count && 'result_schema_version' in result) assert.equal(result.benchmarks[0]!.observations.length, item.sample_observation_count);
  assert.deepEqual(readConsumerResult(writeConsumerResult(result)), result);
  if (item.legacy_numeric_projection) assert.throws(() => projectLegacy(result), /legacy_projection_unrepresentable/u);
  assert.equal(await read(item.source), source);
});
for (const item of (JSON.parse(await read('strict-json-cases.json')) as {cases:{id:string; source:string; strict_json:string; consumer?:string}[]}).cases) test(`strict JSON ${item.id}`, () => {
  if (item.strict_json === 'reject') assert.throws(() => strictJson(item.source));
  else { strictJson(item.source); if (item.consumer === 'reject') assert.throws(() => readConsumerResult(item.source)); }
});
test('legacy projection refuses shared invalid counts and enum coercions', async () => {
  const original = JSON.parse(await read('legacy-zero.json')) as Record<string, unknown>;
  const cases = JSON.parse(await read('invalid-legacy-projections.json')) as {changes:Record<string,unknown>[]};
  for (const change of cases.changes) assert.throws(() => projectLegacy(readConsumerResult(JSON.stringify({...original, ...change}))), /legacy_projection_unrepresentable/u);
  const zero = projectLegacy(readConsumerResult(await read('legacy-zero.json')));
  assert.equal(zero['overall_score'], 0);
});
test('collection failures reject array enum and duplicate logical identity', () => {
  const failure = {run_id:'r', model_id:'m', execution:'failed', reason:'result_projection_unavailable', artifacts:[], eligibility:{eligible:false,reasons:['result_projection_unavailable']}};
  const collection = {result_collection_schema_version:'1', results:[], failures:[failure]};
  readConsumerResult(JSON.stringify(collection));
  assert.throws(() => readConsumerResult(JSON.stringify({...collection,failures:[{...failure,execution:['failed']}]})));
  assert.throws(() => readConsumerResult(JSON.stringify({...collection,failures:[failure,failure]})));
});
test('report wrapper cannot promote an ineligible source or missing policy', async () => {
  const source = readConsumerResult(await read('../v2/named-metrics.json'));
  const report = {recommendation_schema_version:'2',status:'no_recommendation', recommendations:{},model_scores:{},best_overall:null,best_balanced:null,exclusions:[],sources:[source],policy:null,judge_controls:[],limitations:[]};
  readRecommendationReport(JSON.stringify(report));
  assert.throws(() => readRecommendationReport(JSON.stringify({...report,status:['no_recommendation']})));
  assert.throws(() => readRecommendationReport(JSON.stringify({...report,status:'recommended', recommendations:{accuracy:{status:'recommended',recommended:'fake',score:1,alternatives:[],units:'fraction',direction:'higher',reasons:[]}}})));
});

test('public evaluate invokes actual CLI run and preserves native nullable measurements', {timeout:120000}, async () => {
  const directory = await mkdtemp(join(tmpdir(), 'matric consumer boundary '));
  let python = process.env['MATRIC_EVAL_TEST_PYTHON'] ?? join(root, '.venv/bin/python');
  try { await access(python); } catch { python = '/usr/bin/env python3'; }
  const executable = join(directory, 'actual cli');
  // Registration is test-only; dispatch, engine, Inspect scoring, stdout and readers are real.
  await writeFile(executable, `#!${python}\nimport sys\nsys.path.insert(0, ${JSON.stringify(root)})\nfrom tests.consumer_cli_fixture import main\nmain()\n`, {mode:0o755});
  try {
    const client = createClient(executable);
    const result = await client.evaluate({resultFormat:'v2',tier:'smoke',models:['mockllm/model'],benchmarks:['consumer_fixture'],outputDir:join(directory,'result files')});
    assert.ok('result_schema_version' in result);
    assert.equal(result.model_id, 'mockllm/model');
    assert.equal(result.overall_estimate.value, null);
    assert.equal(result.benchmarks[0]!.primary_estimate.value, 0.5);
    assert.deepEqual(result.benchmarks[0]!.observations.map(row => row.value).sort(), [0,1]);
    assert.equal(result.comparability?.eligibility.eligible, false);
    assert.ok(Object.keys(result.benchmarks[0]!.metrics).length >= 2);
    assert.deepEqual(readConsumerResult(writeConsumerResult(result)), result);
  } finally { await rm(directory, {recursive:true,force:true}); }
});

// Compile-only overload coverage for existing typed options and literal v2 selection.
function overloads(options: EvalOptions): void {
  const client = createClient();
  const dynamic: Promise<EvalSummary | VersionedEvaluation> = client.run(options);
  const versioned: Promise<VersionedEvaluation> = client.evaluate({resultFormat:'v2'});
  const legacy: Promise<EvalSummary> = client.run();
  void dynamic; void versioned; void legacy;
}
void overloads;

test('recommendation values are bound to declared native reductions and thresholds', async () => {
  const {comparisonInputs} = await import('../result-contract.js');
  const source = readConsumerResult(await read('../v2/named-metrics.json'));
  assert.ok('result_schema_version' in source);
  source.configuration_sha256 = 'b'.repeat(64);
  source.comparability = null;
  source.benchmarks[0]!.protocol_sha256 = 'a'.repeat(64);
  for (const selection of source.benchmarks[0]!.selection) selection.data.role = 'final_test';
  const payload = JSON.stringify(comparisonInputs(source));
  source.comparability = {version:'1',payload,sha256:createHash('sha256').update(payload).digest('hex'),eligibility:{eligible:true,reasons:[]}};
  const declaration = {version:'1',aggregation_id:'fixture/1',target_units:'fraction',target_direction:'higher',missingness_policy:'require-complete',terms:[{benchmark_id:'benchmark',metric_id:'exact/accuracy',weight:1,transform:{version:'1',kind:'identity',source_units:'fraction',source_minimum:0,source_maximum:1,source_direction:'higher',scale:1,offset:0}}]};
  const report = {recommendation_schema_version:'2',status:'recommended',sources:[source],policy:{version:'1',comparison_sha256:source.comparability.sha256,capabilities:{accuracy:declaration},minimum_score:null as number|null,require_qualified_judges:false},exclusions:[],judge_controls:[],limitations:[],best_overall:null,best_balanced:null,model_scores:{[source.model_id]:{model:source.model_id,run_id:source.run_id,benchmark_scores:{benchmark:0.5},capability_scores:{accuracy:0.5},overall_score:null,size_gb:null}},recommendations:{accuracy:{status:'recommended',recommended:source.model_id,score:0.5,alternatives:[],units:'fraction',direction:'higher',reasons:[]}}};
  readRecommendationReport(JSON.stringify(report));
  readRecommendationReport(JSON.stringify({...report,sources:[source,source]}));
  const forged = structuredClone(report);
  forged.model_scores[source.model_id]!.capability_scores.accuracy = 999;
  forged.recommendations.accuracy.score = 999;
  assert.throws(() => readRecommendationReport(JSON.stringify(forged)), /invalid_recommendation_report/u);
  report.policy.minimum_score = 0.6;
  assert.throws(() => readRecommendationReport(JSON.stringify(report)), /invalid_recommendation_report/u);
  report.policy.minimum_score = null;
  report.policy.capabilities.accuracy.terms[0]!.transform.source_units = 'percent';
  assert.throws(() => readRecommendationReport(JSON.stringify(report)), /invalid_recommendation_report/u);
});

test('report annotations reject primitive exclusions and invented judge qualification', () => {
  const report = {recommendation_schema_version:'2',status:'no_recommendation', recommendations:{},model_scores:{},best_overall:null,best_balanced:null,exclusions:[],sources:[],policy:null,judge_controls:[],limitations:[]};
  for (const change of [{exclusions:[false]}, {judge_controls:[7]}, {judge_controls:[{qualification:'verified'}]}]) assert.throws(() => readRecommendationReport(JSON.stringify({...report,...change})));
});
