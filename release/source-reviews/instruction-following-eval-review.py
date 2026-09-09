import ast
import collections
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

src=Path('/srv/matric-eval/cache/uv-calver-final/git-v0/checkouts/18674cd99ef1c97a/0c495b2')
out=Path('/srv/matric-eval/workspaces/ifeval-source-review-20260908')
dist=md.distribution('instruction-following-eval')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
tracked=subprocess.check_output(['git','-C',str(src),'ls-files'],text=True).splitlines()
source_files=[{'path':p,'sha256':sha(src/p)} for p in tracked]
installed_files=[]
for p in dist.files:
    name=str(p)
    if name.startswith('instruction_following_eval/') and '__pycache__' not in name:
        installed_files.append({'path':name,'sha256':sha(Path(dist.locate_file(p)))})
installed_files.sort(key=lambda x:x['path'])
assert {x['path']:x['sha256'] for x in installed_files}=={x['path']:x['sha256'] for x in source_files if x['path'].startswith('instruction_following_eval/')}
calls={}
for p in tracked:
    if p.endswith('.py'):
        tree=ast.parse((src/p).read_text())
        calls[p]=sorted(set(ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)))
import nltk.data
sentinel=object()
with patch.object(nltk.data,'switch_punkt',return_value=sentinel) as switch, patch.object(nltk.data,'_open',side_effect=AssertionError('pickle opened')):
    assert nltk.data.load('nltk:tokenizers/punkt/english.pickle',cache=False) is sentinel
    switch.assert_called_once_with('english')
from instruction_following_eval.evaluation import test_instruction_following
payload="__import__('os').system('id')"
result=test_instruction_following({'key':1,'prompt':'fixture','instruction_id_list':['punctuation:no_comma'],'kwargs':[{}]},payload)
assert result.follow_instruction_list==[True]
bandit=json.loads((out/'bandit.json').read_text())
summary=collections.Counter(x['test_id'] for x in bandit['results'])
record={'source_files':source_files,'installed_files':installed_files,'direct_url':json.loads(dist.read_text('direct_url.json')),'runtime_versions':{n:md.version(n) for n in ('nltk','inspect-evals','instruction-following-eval')},'nltk_data_sha256':sha(Path(nltk.data.__file__)),'source_payload_sha256':hashlib.sha256(json.dumps(source_files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'bandit_summary':dict(summary),'bandit_errors':bandit['errors'],'bandit_metrics':bandit['metrics']['_totals'],'bounded_checks':{'hardcoded_pickle_path_redirects_without_open':True,'response_python_text_remains_data':True,'models_loaded':0},'ast_calls':calls}
(out/'inventory.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('source_files','installed_files','ast_calls')},indent=2))
