# Deployment Plan

## Overview

matric-eval is a Python package with language bindings, distributed through multiple channels to support local development, CI/CD automation, and cross-language integrations.

## Release Strategy

### Versioning

**Semantic Versioning (SemVer)**: MAJOR.MINOR.PATCH

- **MAJOR**: Breaking API changes, incompatible benchmark updates
- **MINOR**: New benchmarks, new features, backward-compatible changes
- **PATCH**: Bug fixes, documentation updates, minor improvements

**Version Examples**:
- `0.1.0` - Initial alpha release
- `0.2.0` - Add GSM8K benchmark
- `0.2.1` - Fix MBPP function extraction
- `1.0.0` - Stable API, production ready
- `2.0.0` - Breaking change to task interface

**Pre-release Tags**:
- `0.1.0-alpha.1` - Early testing
- `0.1.0-beta.1` - Feature complete, stabilization
- `0.1.0-rc.1` - Release candidate

### Release Cadence

- **Patch releases**: As needed for critical fixes
- **Minor releases**: Every 2-4 weeks during active development
- **Major releases**: When breaking changes are necessary

## Distribution Channels

### 1. Python Package (pip/uv)

**Primary Distribution**: PyPI (Python Package Index)

**Installation**:
```bash
# Production release
pip install matric-eval

# Specific version
pip install matric-eval==0.2.1

# Development install
uv pip install -e /path/to/matric-eval

# With optional dependencies
pip install matric-eval[dev]  # Development tools
pip install matric-eval[all]  # All optional features
```

**Package Metadata** (`pyproject.toml`):
```toml
[project]
name = "matric-eval"
version = "0.1.0"
description = "Consolidated model evaluation framework for Ollama"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "matric team", email = "dev@integrolabs.net"}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "inspect-ai>=0.3.0",
    "ollama>=0.1.0",
    "click>=8.1.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
]

[project.scripts]
matric-eval = "matric_eval.cli:main"

[project.urls]
Homepage = "https://git.integrolabs.net/roctinam/matric-eval"
Repository = "https://git.integrolabs.net/roctinam/matric-eval"
Issues = "https://git.integrolabs.net/roctinam/matric-eval/issues"
```

**Build Process**:
```bash
# Build wheel and source distribution
uv build

# Output: dist/matric_eval-0.1.0-py3-none-any.whl
#         dist/matric_eval-0.1.0.tar.gz
```

**Upload to PyPI**:
```bash
# Test PyPI first
uv publish --repository testpypi

# Production PyPI
uv publish
```

### 2. TypeScript Bindings (npm)

**Package**: `@matric/eval`

**Installation**:
```bash
# Production
npm install @matric/eval

# Development
npm link /path/to/matric-eval/bindings/typescript
```

**Package Structure** (`bindings/typescript/package.json`):
```json
{
  "name": "@matric/eval",
  "version": "0.1.0",
  "description": "TypeScript bindings for matric-eval",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "test": "jest",
    "prepublishOnly": "npm run build"
  },
  "peerDependencies": {
    "matric-eval": ">=0.1.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "typescript": "^5.3.0",
    "jest": "^29.0.0"
  },
  "repository": {
    "type": "git",
    "url": "https://git.integrolabs.net/roctinam/matric-eval",
    "directory": "bindings/typescript"
  }
}
```

**Integration Pattern**:
```typescript
// Subprocess execution of Python CLI
import { spawn } from 'child_process';

export async function runEvaluation(options: EvalOptions): Promise<EvalResult> {
  const args = [
    '-m', 'matric_eval',
    '--tier', options.tier,
    '--model', options.model,
    '--format', 'json',
  ];

  const proc = spawn('python', args);
  // Parse JSON output from stdout
}
```

**Publishing**:
```bash
cd bindings/typescript
npm publish --access public
```

### 3. Rust Bindings (Future - crates.io)

**Package**: `matric-eval`

**Installation**:
```toml
[dependencies]
matric-eval = "0.1"
```

**Integration Pattern**: FFI or subprocess (TBD in Phase 2)

## Deployment Targets

### 1. Local Development Machines

**Target Users**: Developers working on matric-cli, matric-memory, or matric-eval itself

**Installation**:
```bash
# Standard installation
pip install matric-eval

# Editable development mode
git clone https://git.integrolabs.net/roctinam/matric-eval
cd matric-eval
uv pip install -e .
```

**Configuration**:
- `.matric-eval.yaml` in home directory or project root
- Environment variables: `MATRIC_EVAL_*`
- CLI arguments override config files

**Verification**:
```bash
matric-eval --version
matric-eval --tier smoke --model llama3.2:3b
```

### 2. CI/CD Runners (Gitea Actions)

**Target**: Automated testing in matric-eval and consuming projects

**Installation in Workflow**:
```yaml
- name: Install matric-eval
  run: |
    pip install matric-eval==0.2.1
    matric-eval --version
```

**Caching**:
```yaml
- name: Cache Python dependencies
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
```

**Artifact Storage**:
- Test results: `results/*.json`
- Coverage reports: `.coverage`, `htmlcov/`
- SBOM: `sbom.json`

### 3. matric-cli Integration

**Target**: TypeScript project using subprocess calls

**Installation**:
```bash
# In matric-cli
npm install @matric/eval
```

**Runtime Requirements**:
- Python 3.11+ in PATH
- `matric-eval` package installed
- Ollama server accessible

**Usage Example**:
```typescript
import { evaluate } from '@matric/eval';

const result = await evaluate({
  tier: 'quick',
  model: 'llama3.2:3b',
  benchmarks: ['humaneval', 'mbpp'],
});

console.log(`Pass rate: ${result.passRate}`);
```

### 4. matric-memory Integration

**Target**: Rust project using subprocess calls (Phase 2)

**Installation**:
```toml
[dependencies]
matric-eval = "0.1"
```

**Runtime Requirements**: Same as matric-cli

## Installation Instructions

### Prerequisites

**System Requirements**:
- Python 3.11 or higher
- 2GB RAM minimum (4GB+ recommended for full evaluations)
- Ollama server running (local or remote)
- Network access to download models and datasets

**Check Prerequisites**:
```bash
python --version  # Should be 3.11+
ollama --version  # Should be installed
ollama list       # Verify server is running
```

### Standard Installation

**Step 1: Install Package**:
```bash
pip install matric-eval
```

**Step 2: Verify Installation**:
```bash
matric-eval --version
matric-eval --help
```

**Step 3: Download Datasets** (optional, auto-downloads on first use):
```bash
matric-eval --download-datasets
```

**Step 4: Run Smoke Test**:
```bash
matric-eval --tier smoke --model llama3.2:3b
```

### Development Installation

**Step 1: Clone Repository**:
```bash
git clone https://git.integrolabs.net/roctinam/matric-eval
cd matric-eval
```

**Step 2: Install with uv**:
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

**Step 3: Verify Development Setup**:
```bash
pytest
ruff check .
mypy src/
```

### TypeScript Bindings Installation

**In matric-cli or other TypeScript project**:
```bash
npm install @matric/eval
```

**Verify TypeScript Integration**:
```typescript
import { version } from '@matric/eval';
console.log(`matric-eval version: ${version}`);
```

## Upgrade Path

### Patch Upgrades (0.1.0 → 0.1.1)

**No Breaking Changes** - Safe to upgrade immediately

```bash
# Upgrade Python package
pip install --upgrade matric-eval

# Upgrade TypeScript bindings
npm update @matric/eval
```

**Verification**:
```bash
matric-eval --version
# Re-run existing evaluations to verify consistency
```

### Minor Upgrades (0.1.x → 0.2.0)

**New Features, Backward Compatible**

**Migration Steps**:
1. Review changelog for new features
2. Update configuration if using new options
3. Upgrade package
4. Test with existing workflows

```bash
# Check what's new
pip show matric-eval

# Upgrade
pip install --upgrade matric-eval

# Verify existing workflows still work
matric-eval --tier smoke --model llama3.2:3b
```

**New Features Available**:
- Check documentation for new benchmarks
- Review new CLI options with `--help`
- Update configs to use new capabilities

### Major Upgrades (0.x.x → 1.0.0)

**Breaking Changes - Requires Migration**

**Pre-Upgrade Checklist**:
1. Read migration guide in CHANGELOG.md
2. Review breaking changes list
3. Backup existing results and configs
4. Test in non-production environment first

**Migration Process**:

**Step 1: Backup**:
```bash
# Backup results
cp -r results/ results.backup/

# Backup configs
cp .matric-eval.yaml .matric-eval.yaml.backup
```

**Step 2: Upgrade in Test Environment**:
```bash
# Create test virtualenv
python -m venv test-upgrade
source test-upgrade/bin/activate
pip install matric-eval==1.0.0
```

**Step 3: Migrate Configuration**:
```bash
# Use migration tool (if provided)
matric-eval migrate-config --from 0.9 --to 1.0

# Or manually update based on changelog
```

**Step 4: Test Migration**:
```bash
# Run smoke tests
matric-eval --tier smoke --model llama3.2:3b

# Compare results with previous version
diff results/smoke-v0.9.json results/smoke-v1.0.json
```

**Step 5: Deploy to Production**:
```bash
# Upgrade main environment
pip install --upgrade matric-eval==1.0.0

# Update CI/CD pipelines
# Update dependent projects (matric-cli, matric-memory)
```

**Step 6: Update Dependent Projects**:

For **matric-cli**:
```bash
cd /home/roctinam/dev/matric-cli
npm update @matric/eval
npm test
```

For **matric-memory** (Phase 2):
```bash
cd /home/roctinam/dev/matric-memory
cargo update matric-eval
cargo test
```

## Rollback Procedures

### Python Package Rollback

**Scenario**: Version 0.2.1 has a critical bug, need to rollback to 0.2.0

**Step 1: Identify Current Version**:
```bash
pip show matric-eval
```

**Step 2: Downgrade**:
```bash
pip install matric-eval==0.2.0
```

**Step 3: Verify**:
```bash
matric-eval --version
# Should show 0.2.0

# Re-run tests
matric-eval --tier smoke --model llama3.2:3b
```

**Step 4: Pin Version in Requirements**:
```bash
# In requirements.txt or pyproject.toml
matric-eval==0.2.0  # Pin to known-good version
```

### TypeScript Bindings Rollback

**Step 1: Downgrade npm Package**:
```bash
npm install @matric/eval@0.1.0
```

**Step 2: Update package.json**:
```json
{
  "dependencies": {
    "@matric/eval": "0.1.0"
  }
}
```

**Step 3: Verify Integration**:
```bash
npm test
```

### CI/CD Pipeline Rollback

**Scenario**: New version breaks CI/CD pipeline

**Step 1: Identify Failing Build**:
```bash
# Check Gitea Actions logs
# Identify version that introduced failure
```

**Step 2: Update Workflow File**:
```yaml
# .gitea/workflows/test.yml
- name: Install matric-eval
  run: |
    pip install matric-eval==0.1.9  # Rollback from 0.2.0
```

**Step 3: Commit and Push**:
```bash
git add .gitea/workflows/test.yml
git commit -m "fix(ci): rollback matric-eval to 0.1.9"
git push
```

**Step 4: Verify Pipeline**:
- Check Gitea Actions dashboard
- Confirm tests pass

### Emergency Rollback (Critical Production Issue)

**Immediate Actions**:

1. **Stop New Deployments**:
```bash
# Halt any running deployments
# Notify team in chat/issue tracker
```

2. **Rollback All Environments**:
```bash
# Production
pip install matric-eval=={LAST_KNOWN_GOOD_VERSION}

# CI/CD
# Update all workflow files with pinned version
```

3. **Restore Configurations**:
```bash
# Restore backed-up configs
cp .matric-eval.yaml.backup .matric-eval.yaml
```

4. **Verify Rollback**:
```bash
matric-eval --version
matric-eval --tier smoke --model llama3.2:3b
```

5. **Create Incident Report**:
- Document issue in Gitea Issues
- Root cause analysis
- Prevention plan

### Rollback Verification Checklist

- [ ] Version number correct (`matric-eval --version`)
- [ ] Smoke tests pass
- [ ] Quick tier evaluation works
- [ ] TypeScript bindings compatible (if applicable)
- [ ] CI/CD pipeline green
- [ ] No data loss in results directory
- [ ] Configurations valid
- [ ] Dependent projects tested

## Version Pinning Strategies

### For Production Stability

**Exact Pinning**:
```toml
# pyproject.toml
dependencies = [
    "matric-eval==0.2.1",  # Exact version
]
```

**Pros**: Maximum stability, predictable behavior
**Cons**: Manual upgrades required, miss security patches

### For Active Development

**Compatible Release**:
```toml
dependencies = [
    "matric-eval~=0.2.0",  # >= 0.2.0, < 0.3.0
]
```

**Pros**: Get patch updates automatically
**Cons**: Small risk of regression from patches

### For CI/CD

**Lock File Approach**:
```bash
# Generate lock file
uv pip freeze > requirements.lock

# Install from lock
pip install -r requirements.lock
```

**Pros**: Reproducible builds, controlled upgrades
**Cons**: Requires lock file maintenance

## Distribution Checklist

### Pre-Release

- [ ] Version bumped in `pyproject.toml`
- [ ] CHANGELOG.md updated with release notes
- [ ] All tests passing (`pytest`)
- [ ] Coverage above 80% threshold
- [ ] Type checking passes (`mypy`)
- [ ] Linting clean (`ruff check`)
- [ ] Documentation updated
- [ ] Migration guide written (for breaking changes)
- [ ] SBOM generated

### Python Package Release

- [ ] Build package (`uv build`)
- [ ] Test on TestPyPI (`uv publish --repository testpypi`)
- [ ] Install from TestPyPI and verify
- [ ] Publish to PyPI (`uv publish`)
- [ ] Create Git tag (`git tag v0.2.1`)
- [ ] Push tag (`git push --tags`)
- [ ] Create GitHub/Gitea release with notes

### TypeScript Bindings Release

- [ ] Update version in `package.json`
- [ ] Build TypeScript (`npm run build`)
- [ ] Run TypeScript tests (`npm test`)
- [ ] Publish to npm (`npm publish`)
- [ ] Verify installation from npm

### Post-Release

- [ ] Update documentation site
- [ ] Announce in team channels
- [ ] Update dependent projects (matric-cli, matric-memory)
- [ ] Monitor for issues in first 24 hours
- [ ] Update internal wikis/runbooks

## Dependency Management

### Python Dependencies

**Core Dependencies** (minimal):
- inspect-ai: Evaluation framework
- ollama: Model client
- click: CLI interface
- pydantic: Configuration validation

**Update Strategy**:
```bash
# Check for outdated packages
pip list --outdated

# Update dependencies
uv pip install --upgrade inspect-ai ollama click pydantic

# Test after updates
pytest
```

**Security Scanning**:
```bash
# Scan for vulnerabilities
pip-audit

# Generate SBOM
cyclonedx-py -o sbom.json
```

### Benchmark Dataset Versions

**Version Management**:
```yaml
# datasets/versions.yaml
humaneval:
  version: "1.0.0"
  sha256: "abc123..."
  url: "https://github.com/openai/human-eval/releases/v1.0.0"

mbpp:
  version: "1.0.1"
  sha256: "def456..."
  url: "https://huggingface.co/datasets/mbpp/resolve/main/mbpp.jsonl"
```

**Update Process**:
1. New dataset version released
2. Download and verify checksum
3. Run validation tests
4. Update `versions.yaml`
5. Document changes in CHANGELOG

## Environment Configuration

### Development Environment

**.env.development**:
```bash
MATRIC_EVAL_LOG_LEVEL=DEBUG
MATRIC_EVAL_OLLAMA_URL=http://localhost:11434
MATRIC_EVAL_CACHE_DIR=/tmp/matric-eval-cache
MATRIC_EVAL_RESULTS_DIR=./results
```

### CI/CD Environment

**.env.ci**:
```bash
MATRIC_EVAL_LOG_LEVEL=INFO
MATRIC_EVAL_OLLAMA_URL=http://ollama:11434
MATRIC_EVAL_RESULTS_DIR=/workspace/results
MATRIC_EVAL_CACHE_ENABLED=false
```

### Production Environment

**For Consuming Projects**:
```bash
# In matric-cli or matric-memory
MATRIC_EVAL_LOG_LEVEL=WARNING
MATRIC_EVAL_TIMEOUT=600
MATRIC_EVAL_MAX_RETRIES=3
```

## Monitoring Post-Deployment

### Success Metrics

- [ ] Download count (PyPI stats)
- [ ] Import success rate (no errors)
- [ ] Test pass rate in CI/CD
- [ ] Issue reports vs. downloads ratio
- [ ] Time to upgrade (adoption rate)

### Health Checks

**Daily**:
```bash
# Automated health check in CI
matric-eval --tier smoke --model llama3.2:3b
```

**Weekly**:
```bash
# Full regression test
matric-eval --tier quick --model llama3.2:3b
```

**Monthly**:
```bash
# Comprehensive evaluation
matric-eval --tier full
```

## Support and Troubleshooting

### Common Issues

**Issue**: `ModuleNotFoundError: No module named 'matric_eval'`
**Solution**:
```bash
pip install matric-eval
# or
pip install --force-reinstall matric-eval
```

**Issue**: Version mismatch between Python and TypeScript
**Solution**:
```bash
# Check versions
pip show matric-eval
npm list @matric/eval

# Align versions
npm install @matric/eval@0.2.1
```

**Issue**: Ollama connection errors
**Solution**:
```bash
# Check Ollama is running
ollama list

# Set custom URL
export MATRIC_EVAL_OLLAMA_URL=http://custom-host:11434
```

### Getting Help

1. **Documentation**: Check README.md and docs/
2. **Issues**: https://git.integrolabs.net/roctinam/matric-eval/issues
3. **Logs**: Enable debug logging with `MATRIC_EVAL_LOG_LEVEL=DEBUG`
4. **Community**: Team chat or email

## Future Enhancements

### Phase 2 (v0.3.0+)

- Rust bindings on crates.io
- Docker container distribution
- Hosted evaluation service
- Web dashboard for results

### Phase 3 (v1.0.0+)

- Private benchmark repository support
- Multi-cloud deployment (AWS, GCP, Azure)
- Scheduled evaluation service
- Cost optimization recommendations

## References

- [Python Packaging User Guide](https://packaging.python.org/)
- [Semantic Versioning](https://semver.org/)
- [PyPI Publishing Guide](https://packaging.python.org/tutorials/packaging-projects/)
- [npm Publishing Guide](https://docs.npmjs.com/packages-and-modules/contributing-packages-to-the-registry)
- [PLANNING.md](../../PLANNING.md) - Project architecture
