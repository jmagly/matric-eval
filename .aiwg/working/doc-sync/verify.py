"""Bounded verification for the 2026-09-06 code-to-docs sync; no inference calls."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json
import re
import shlex
import tempfile

from click import Context
from markdown_it import MarkdownIt
import yaml
from matric_eval.cli import cli
from matric_eval.discovery import DatasetManifest, load_manifest
from matric_eval.providers.matrix import EvaluationMatrix

root = Path.cwd()
files = ['README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'WORKSPACE.md',
         'docs/README.md', 'docs/cli.md', 'docs/architecture/overview.md',
         'docs/development/session-init.md']
parser = MarkdownIt('commonmark')
links = 0

def anchors(path):
    text = path.read_text()
    values = set()
    for title in re.findall(r'^#{1,6}\s+(.+)$', text, re.M):
        title = re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-')
        values.add(title)
    return values

for name in files:
    path = root / name
    tokens = parser.parse(path.read_text())
    for token in tokens:
        for child in token.children or []:
            if child.type != 'link_open':
                continue
            url = child.attrGet('href')
            u = urlsplit(url)
            if u.scheme:
                prefix = 'https://github.com/jmagly/matric-eval/'
                if not url.startswith(prefix):
                    continue
                route = u.path.split('/')[3:]
                if len(route) < 3 or route[0] not in ('blob', 'tree'):
                    continue
                target = root / unquote('/'.join(route[2:]))
            else:
                target = path.parent / unquote(u.path) if u.path else path
            if name == 'WORKSPACE.md' and u.path == '.aiwg/quickref.json':
                assert '(when configured)' in path.read_text()
                continue
            assert target.exists(), (name, url, str(target))
            if u.fragment and target.suffix == '.md':
                assert unquote(u.fragment) in anchors(target), (name, url, 'missing anchor')
            links += 1

reference = (root/'docs/cli.md').read_text()
with Context(cli, info_name='matric-eval') as ctx:
    assert cli.get_help(ctx) in reference
    for name, command in cli.commands.items():
        with Context(command, info_name=name, parent=ctx) as sub:
            assert command.get_help(sub) in reference, name

readme = (root/'README.md').read_text()
required_sections = ['What matric-eval Does', 'Status', 'Installation', 'Quick Start',
                     'Features', 'Inference Providers', 'Benchmarks and Tiers',
                     'Evaluation Matrix', 'Custom Datasets', 'Preregistered Studies',
                     'TypeScript Client', 'Architecture', 'Execution Safety',
                     'Troubleshooting', 'Documentation', 'Contributing',
                     'Community & Support', 'License', 'Acknowledgments']
for heading in required_sections:
    assert f'## {heading}\n' in readme, heading
assert readme.count('<div align="center">') == readme.count('</div>') == 2
assert '[**Back to Top**](#matric-eval)' in readme
assert 'img.shields.io' in readme
assert 'integrolabs.io' in readme

# Parse real example commands using Click, with local fixture paths for path checks.
command_count = 0
with tempfile.TemporaryDirectory() as temporary:
    tmp = Path(temporary)
    matrix_file = tmp / 'eval-matrix.yaml'
    yaml_blocks = [t.content for t in parser.parse(readme) if t.type == 'fence' and t.info == 'yaml']
    matrix_file.write_text(yaml_blocks[0])
    matrix = EvaluationMatrix.from_yaml(matrix_file)
    assert len(matrix.get_runs()) == 2
    manifest_path = tmp / 'dataset.yaml'
    manifest_path.write_text(yaml_blocks[1])
    manifest = load_manifest(manifest_path)
    assert manifest.name == 'my-eval' and manifest.field_mapping == {'input':'question','target':'answer'}
    assert DatasetManifest().tiers.smoke == 10
    for token in parser.parse(readme):
        if token.type != 'fence' or token.info != 'bash':
            continue
        content = token.content.replace('\\\n', ' ')
        for line in content.splitlines():
            if not line.startswith('uv run matric-eval '):
                continue
            args = shlex.split(line)[3:]
            if args == ['--help'] or args == ['--version']:
                continue
            name, *params = args
            assert name in cli.commands, name
            params = [str(matrix_file) if p == 'eval-matrix.yaml' else str(tmp) if p == 'results/RUN_ID' else p for p in params]
            with cli.commands[name].make_context(name, params):
                pass
            command_count += 1

jsonl = next(t.content for t in parser.parse(readme) if t.type == 'fence' and t.info == 'jsonl')
assert json.loads(jsonl)['target'] == '4'
result = {'files': files, 'checked_links': links, 'cli_help_commands': len(cli.commands),
          'readme_commands_parsed': command_count, 'matrix_runs': 2,
          'readme_sections': required_sections, 'status': 'passed',
          'scope_note': 'Local and repository-target links checked; no external URL availability or live inference validation.'}
(root/'.aiwg/working/doc-sync/verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
