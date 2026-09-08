"""Bounded real study-model readiness qualification; no scoring requests."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

workspace = Path('/srv/matric-eval/workspaces/matric-eval-160-model-qualification')
python = Path('/srv/matric-eval/workspaces/matric-eval-157-status/.venv311/bin/python')
study = Path('/srv/matric-eval/results/qwen38-obliteration-2026-09')
base = study / 'run-control' / f'storage160-qualification-{time.time_ns()}'
base.mkdir(mode=0o700)
(base / 'ledger').mkdir(mode=0o700)
(base / 'volumes').mkdir(mode=0o700)
model_root = Path('/srv/obliteratus/matric-eval/cache/huggingface/hub/models--Qwen--Qwen3.8-27B')
model_path = model_root / 'snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
gpu = 'GPU-fc9d264d-8a20-bf8c-eb72-72a6dcbdaf2a'
model_id = 'qwen38-27b-source-bf16'
port = 18091
sizes = {'temporary': 8*2**30, 'download_cache': 16*2**30, 'scratch': 8*2**30, 'logs': 64*2**20, 'evidence': 256*2**20}
mounts = []
for kind, size in sizes.items():
    path = base / 'volumes' / kind
    path.mkdir(mode=0o700)
    if kind == 'evidence':
        backing = base / 'evidence.ext4'
        with backing.open('xb') as output:
            output.truncate(size)
        subprocess.run(['mkfs.ext4', '-q', '-F', '-N', '8192', str(backing)], check=True)
        subprocess.run(['mount', '-o', 'loop,nosuid,nodev', str(backing), str(path)], check=True)
    else:
        subprocess.run(['mount', '-t', 'tmpfs', '-o', f'size={size},nr_inodes=65536,mode=0700', f'matric160-{kind}', str(path)], check=True)
    mounts.append(path)
allocations = [{'kind': kind, 'path': str(base/'volumes'/kind), 'budget_bytes': size, 'budget_inodes': 8192 if kind == 'evidence' else 65536, 'estimated_bytes': None, 'disposable': kind in ('scratch','temporary','download_cache')} for kind,size in sizes.items()]
allocations += [
    {'kind':'models','path':str(model_root),'budget_bytes':0,'budget_inodes':0,'estimated_bytes':0},
    {'kind':'docker','path':'/srv/obliteratus/matric-eval/docker/data','budget_bytes':256*2**20,'budget_inodes':65536,'estimated_bytes':64*2**20},
]
config={'allocations':allocations,'ledger':str(base/'ledger'),'ownership':str(base),'headroom_bytes':10*2**30,'headroom_inodes':65536}
(base/'storage.json').write_text(json.dumps(config))
check=base/'check.py'
check.write_text('''import json,os,pathlib,subprocess,sys,urllib.request
from matric_eval.studies.protocol import StudyProtocol
from matric_eval.studies.batch import _model_for_id,verify_model_artifact
from matric_eval.studies.resource_lifecycle import Broker,Docker
stage,workspace,base,model_path,model_id,port=sys.argv[1:]
workspace=pathlib.Path(workspace); base=pathlib.Path(base); study=pathlib.Path('/srv/matric-eval/results/qwen38-obliteration-2026-09')
if stage=='static':
 protocol=StudyProtocol.from_yaml(workspace/'studies/qwen38-obliteration-2026-09/protocol.yaml',validate_registry=False)
 verify_model_artifact(_model_for_id(protocol,model_id),pathlib.Path(model_path),json.loads((study/'source-model-qualification.json').read_text()),verify_tensor_hashes=True)
elif stage=='cpu':
 subprocess.run([sys.executable,'-m','matric_eval.studies.server_cli','--help'],check=True,capture_output=True,timeout=15)
elif stage=='auxiliary':
 assert isinstance(Broker('/run/ollama-unify/gpu-negotiator.sock').call('status')['leases'],list)
else:
 with urllib.request.urlopen('http://127.0.0.1:'+port+'/v1/models',timeout=10) as response: models=json.load(response)
 assert model_id in {item['id'] for item in models['data']}
 record=json.loads((base/'resources'/'record.json').read_text()); docker=Docker('unix:///run/matric-eval-docker.sock'); info=docker.inspect(record['container'])
 assert info['Config']['Labels']['matric.resource']==record['resource_id']
 assert any(gpu in record['gpu_uuids'] and info['Id'] in docker.cgroup(pid) for gpu,pid in docker.cuda())
pathlib.Path(os.environ['MATRIC_PREFLIGHT_RECEIPT']).write_text(json.dumps({'schema':'storage-model-qualification/1','stage':stage,'passed':True}))
''')
inputs=[str(check),str(study/'source-model-qualification.json'),str(workspace/'studies/qwen38-obliteration-2026-09/protocol.yaml'),str(model_path/'config.json'),str(model_path/'model.safetensors.index.json')]
plan={'schema':'matric-eval.study-preflight/1','checks':[{'id':stage,'stage':stage,'command':[str(python),str(check),stage,str(workspace),str(base),str(model_path),model_id,str(port)],'inputs':inputs,'timeout_seconds':300,'freshness_seconds':1200,'deterministic':False,'receipt_contract':{'schema':'storage-model-qualification/1','stage':stage,'passed':True}} for stage in ('static','cpu','auxiliary','target')]}
(base/'preflight-plan.json').write_text(json.dumps(plan))
evidence=base/'volumes/evidence'
command=['bash',str(workspace/'scripts/serve_qwen38_container.sh'),'--run-id','issue160-model-qualification','--attempt-id',base.name,'--resource-directory',str(base/'resources'),'--preflight-plan',str(base/'preflight-plan.json'),'--storage-plan',str(base/'storage.json'),'--gpu',gpu,'--owner','matric-issue160-qualification','--model-id',model_id,'--model-path',str(model_path),'--qualification',str(study/'source-model-qualification.json'),'--lease-receipt',str(evidence/'lease.private.json'),'--server-receipt',str(evidence/'server.json'),'--port',str(port)]
print(json.dumps({'qualification_root':str(base),'gpu':gpu,'model':model_id,'scoring_requests':0}),flush=True)
root_log=(base/'volumes/logs/controller.log').open('xb')
process=subprocess.Popen(command,cwd=workspace,env={**os.environ,'MATRIC_LIFECYCLE_PYTHON':str(python),'PYTHONDONTWRITEBYTECODE':'1'},stdout=root_log,stderr=subprocess.STDOUT)
ready=False
try:
 deadline=time.monotonic()+1100
 previous=None
 while time.monotonic()<deadline:
  record_path=base/'resources/record.json'
  record=json.loads(record_path.read_text()) if record_path.exists() else {}
  state=record.get('state')
  if state!=previous:
   print(json.dumps({'state':state,'elapsed':1100-(deadline-time.monotonic())}),flush=True); previous=state
  if state=='ready':
   ready=True; time.sleep(3)
   os.kill(record['controller']['pid'],signal.SIGTERM)
   break
  if process.poll() is not None:
   break
  time.sleep(.5)
 else:
  if record.get('controller'):
   os.kill(record['controller']['pid'],signal.SIGTERM)
 process.wait(timeout=120)
finally:
 root_log.close()
record=json.loads((base/'resources/record.json').read_text())
for path in (base/'volumes/logs').iterdir():
 if path.is_file(): shutil.copyfile(path,evidence/path.name)
summary={'ready':ready,'scoring_requests':0,'wrapper_exit':process.returncode,'resource':record,'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=workspace,text=True).strip()}
(base/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary),flush=True)
if not ready or record.get('cleanup')!='complete' or record.get('storage_reservation_active') is not False:
 raise SystemExit(1)
