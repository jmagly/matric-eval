# CI/CD Pipeline Design

## Overview

matric-eval uses Gitea Actions for continuous integration and deployment. The pipeline enforces quality gates, runs multi-tier testing, generates security artifacts, and automates package publishing.

## Pipeline Architecture

```
┌─────────────────┐
│  Pull Request   │
└────────┬────────┘
         │
         ├─→ Lint & Format Check (30s)
         ├─→ Type Checking (45s)
         ├─→ Unit Tests (1m)
         ├─→ Smoke Tests (2m)
         └─→ Coverage Gate (80%+)
                  │
                  ↓
         ┌────────────────┐
         │  Merge to Main │
         └────────┬───────┘
                  │
                  ├─→ Quick Tier Evaluation (20m)
                  ├─→ Security Scan (2m)
                  ├─→ SBOM Generation (1m)
                  ├─→ Build Package (30s)
                  └─→ Integration Tests (5m)
                           │
                           ↓
                  ┌─────────────────┐
                  │  Tagged Release │
                  └────────┬────────┘
                           │
                           ├─→ Full Evaluation (2h)
                           ├─→ Build Artifacts (1m)
                           ├─→ Publish to PyPI (2m)
                           ├─→ Publish TypeScript (1m)
                           └─→ Create Release Notes
```

## Pipeline Stages

### Stage 1: Lint & Format (PR Gate)

**Purpose**: Ensure code quality and consistency

**Triggers**:
- Every push to PR branch
- Nightly on main branch

**Jobs**:

```yaml
# .gitea/workflows/lint.yml
name: Lint and Format

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Cache uv dependencies
        uses: actions/cache@v3
        with:
          path: ~/.cache/uv
          key: ${{ runner.os }}-uv-${{ hashFiles('pyproject.toml') }}

      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.cargo/bin" >> $GITHUB_PATH

      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e ".[dev]"

      - name: Run ruff linter
        run: |
          source .venv/bin/activate
          ruff check . --output-format=github

      - name: Run ruff formatter
        run: |
          source .venv/bin/activate
          ruff format --check .

      - name: Check import sorting
        run: |
          source .venv/bin/activate
          ruff check --select I .

  typecheck:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e ".[dev]"

      - name: Run mypy type checker
        run: |
          source .venv/bin/activate
          mypy src/ --show-error-codes --pretty
```

**Quality Gates**:
- [ ] No linting errors (ruff check)
- [ ] Code formatted correctly (ruff format)
- [ ] Imports sorted (ruff --select I)
- [ ] Type hints valid (mypy)

### Stage 2: Test (PR Gate)

**Purpose**: Validate functionality and maintain test coverage

**Triggers**:
- Every push to PR branch
- Every push to main branch

**Jobs**:

```yaml
# .gitea/workflows/test.yml
name: Test

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    strategy:
      matrix:
        python-version: ['3.11', '3.12']

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e ".[dev]"

      - name: Run unit tests
        run: |
          source .venv/bin/activate
          pytest tests/unit/ -v --cov=src/matric_eval --cov-report=xml --cov-report=term

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: unittests
          name: python-${{ matrix.python-version }}

  smoke-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    services:
      ollama:
        image: ollama/ollama:latest
        ports:
          - 11434:11434

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e .

      - name: Wait for Ollama
        run: |
          timeout 60 bash -c 'until curl -s http://localhost:11434/api/tags; do sleep 2; done'

      - name: Pull test model
        run: |
          docker exec ${{ job.services.ollama.id }} ollama pull llama3.2:3b

      - name: Run smoke tests
        env:
          MATRIC_EVAL_OLLAMA_URL: http://localhost:11434
        run: |
          source .venv/bin/activate
          python run_smoke.py

      - name: Upload smoke test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: smoke-test-results
          path: results/smoke-*.json

  coverage-gate:
    runs-on: ubuntu-latest
    needs: [unit-tests]

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Download coverage reports
        uses: actions/download-artifact@v3

      - name: Check coverage threshold
        run: |
          source .venv/bin/activate
          coverage report --fail-under=80
```

**Quality Gates**:
- [ ] All unit tests pass
- [ ] Test coverage >= 80%
- [ ] Smoke tests pass with llama3.2:3b
- [ ] Tests pass on Python 3.11 and 3.12

### Stage 3: Build (Post-Merge)

**Purpose**: Create distributable packages

**Triggers**:
- Push to main branch
- Tagged releases

**Jobs**:

```yaml
# .gitea/workflows/build.yml
name: Build

on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  build-python:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install build tools
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install build

      - name: Build package
        run: |
          source .venv/bin/activate
          python -m build

      - name: Verify package contents
        run: |
          tar -tzf dist/*.tar.gz | head -20
          unzip -l dist/*.whl | head -20

      - name: Upload Python artifacts
        uses: actions/upload-artifact@v3
        with:
          name: python-package
          path: dist/*
          retention-days: 30

  build-typescript:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'

      - name: Install dependencies
        working-directory: bindings/typescript
        run: npm ci

      - name: Build TypeScript
        working-directory: bindings/typescript
        run: npm run build

      - name: Run TypeScript tests
        working-directory: bindings/typescript
        run: npm test

      - name: Package tarball
        working-directory: bindings/typescript
        run: npm pack

      - name: Upload TypeScript artifacts
        uses: actions/upload-artifact@v3
        with:
          name: typescript-package
          path: bindings/typescript/*.tgz
          retention-days: 30
```

**Artifacts Produced**:
- `matric_eval-{version}-py3-none-any.whl`
- `matric_eval-{version}.tar.gz`
- `matric-eval-{version}.tgz` (TypeScript)

### Stage 4: Security & Compliance (Post-Merge)

**Purpose**: Identify vulnerabilities and generate compliance artifacts

**Triggers**:
- Push to main branch
- Weekly scheduled scan

**Jobs**:

```yaml
# .gitea/workflows/security.yml
name: Security Scan

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'  # Weekly on Monday 2 AM

jobs:
  dependency-scan:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e .

      - name: Run pip-audit
        run: |
          source .venv/bin/activate
          pip install pip-audit
          pip-audit --desc --format json --output audit-report.json
        continue-on-error: true

      - name: Upload audit report
        uses: actions/upload-artifact@v3
        with:
          name: security-audit
          path: audit-report.json

  sbom-generation:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e .

      - name: Generate SBOM
        run: |
          source .venv/bin/activate
          pip install cyclonedx-bom
          cyclonedx-py -o sbom.json --format json

      - name: Validate SBOM
        run: |
          cat sbom.json | jq '.components | length'

      - name: Upload SBOM
        uses: actions/upload-artifact@v3
        with:
          name: sbom
          path: sbom.json

  secret-scan:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Full history for comprehensive scan

      - name: Run gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Security Artifacts**:
- `audit-report.json` - Dependency vulnerability scan
- `sbom.json` - Software Bill of Materials
- Gitleaks report (if secrets found)

**Quality Gates**:
- [ ] No critical vulnerabilities (CVSS >= 9.0)
- [ ] SBOM includes all dependencies
- [ ] No secrets committed to repository

### Stage 5: Integration Tests (Post-Merge)

**Purpose**: Verify cross-language bindings and integration scenarios

**Triggers**:
- Push to main branch
- Tagged releases

**Jobs**:

```yaml
# .gitea/workflows/integration.yml
name: Integration Tests

on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  typescript-integration:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    services:
      ollama:
        image: ollama/ollama:latest
        ports:
          - 11434:11434

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'

      - name: Install Python package
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e .

      - name: Install TypeScript bindings
        working-directory: bindings/typescript
        run: |
          npm ci
          npm run build

      - name: Wait for Ollama
        run: |
          timeout 60 bash -c 'until curl -s http://localhost:11434/api/tags; do sleep 2; done'

      - name: Pull test model
        run: |
          docker exec ${{ job.services.ollama.id }} ollama pull llama3.2:3b

      - name: Run TypeScript integration tests
        working-directory: bindings/typescript
        env:
          MATRIC_EVAL_OLLAMA_URL: http://localhost:11434
        run: npm run test:integration

      - name: Upload integration test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: typescript-integration-results
          path: bindings/typescript/test-results/

  matric-cli-integration:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout matric-eval
        uses: actions/checkout@v3
        path: matric-eval

      - name: Checkout matric-cli
        uses: actions/checkout@v3
        with:
          repository: roctinam/matric-cli
          path: matric-cli

      - name: Install matric-eval
        working-directory: matric-eval
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e .

      - name: Install matric-cli
        working-directory: matric-cli
        run: |
          npm ci
          npm run build

      - name: Run matric-cli eval tests
        working-directory: matric-cli
        run: |
          source ../matric-eval/.venv/bin/activate
          npm run test:eval
```

**Integration Scenarios**:
- TypeScript bindings call Python CLI
- matric-cli integration (if available)
- Configuration file compatibility
- Results format validation

### Stage 6: Quick Evaluation (Post-Merge)

**Purpose**: Regression testing with real models

**Triggers**:
- Push to main branch
- Manual trigger

**Jobs**:

```yaml
# .gitea/workflows/quick-eval.yml
name: Quick Evaluation

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      model:
        description: 'Model to evaluate'
        required: false
        default: 'llama3.2:3b'

jobs:
  quick-eval:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      ollama:
        image: ollama/ollama:latest
        ports:
          - 11434:11434

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install matric-eval
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e .

      - name: Pull model
        run: |
          docker exec ${{ job.services.ollama.id }} ollama pull ${{ github.event.inputs.model || 'llama3.2:3b' }}

      - name: Run quick evaluation
        env:
          MATRIC_EVAL_OLLAMA_URL: http://localhost:11434
        run: |
          source .venv/bin/activate
          matric-eval --tier quick --model ${{ github.event.inputs.model || 'llama3.2:3b' }} --format json --output results/quick-eval.json

      - name: Parse results
        run: |
          cat results/quick-eval.json | jq '.summary'

      - name: Upload evaluation results
        uses: actions/upload-artifact@v3
        with:
          name: quick-eval-results
          path: results/
          retention-days: 90

      - name: Check regression
        run: |
          source .venv/bin/activate
          python scripts/check_regression.py results/quick-eval.json
```

**Regression Checks**:
- Pass rate within 5% of baseline
- No new critical failures
- Performance within acceptable range

### Stage 7: Publish (Tagged Releases Only)

**Purpose**: Publish packages to distribution channels

**Triggers**:
- Git tag matching `v*` (e.g., `v0.2.1`)

**Jobs**:

```yaml
# .gitea/workflows/publish.yml
name: Publish

on:
  push:
    tags:
      - 'v*'

jobs:
  publish-pypi:
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install build tools
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install build twine

      - name: Build package
        run: |
          source .venv/bin/activate
          python -m build

      - name: Verify version matches tag
        run: |
          TAG_VERSION=${GITHUB_REF#refs/tags/v}
          PKG_VERSION=$(python -c "import tomli; print(tomli.load(open('pyproject.toml', 'rb'))['project']['version'])")
          if [ "$TAG_VERSION" != "$PKG_VERSION" ]; then
            echo "Version mismatch: tag=$TAG_VERSION, package=$PKG_VERSION"
            exit 1
          fi

      - name: Publish to Test PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.TEST_PYPI_TOKEN }}
        run: |
          source .venv/bin/activate
          twine upload --repository testpypi dist/*

      - name: Test installation from Test PyPI
        run: |
          pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ matric-eval
          matric-eval --version

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: |
          source .venv/bin/activate
          twine upload dist/*

  publish-npm:
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
          registry-url: 'https://registry.npmjs.org'

      - name: Install dependencies
        working-directory: bindings/typescript
        run: npm ci

      - name: Build package
        working-directory: bindings/typescript
        run: npm run build

      - name: Run tests
        working-directory: bindings/typescript
        run: npm test

      - name: Publish to npm
        working-directory: bindings/typescript
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: npm publish --access public

  create-release:
    runs-on: ubuntu-latest
    needs: [publish-pypi, publish-npm]

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Download artifacts
        uses: actions/download-artifact@v3

      - name: Generate release notes
        run: |
          python scripts/generate_release_notes.py ${{ github.ref_name }} > release-notes.md

      - name: Create GitHub release
        uses: softprops/action-gh-release@v1
        with:
          body_path: release-notes.md
          files: |
            python-package/*
            typescript-package/*
            sbom/sbom.json
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Publishing Checklist**:
- [ ] Version in pyproject.toml matches Git tag
- [ ] Package builds successfully
- [ ] Test installation from Test PyPI works
- [ ] PyPI publication succeeds
- [ ] npm publication succeeds
- [ ] GitHub release created with notes

### Stage 8: Nightly Full Evaluation (Optional)

**Purpose**: Comprehensive model testing for regression detection

**Triggers**:
- Scheduled nightly (2 AM UTC)
- Manual trigger

**Jobs**:

```yaml
# .gitea/workflows/nightly.yml
name: Nightly Full Evaluation

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily
  workflow_dispatch:

jobs:
  full-eval:
    runs-on: ubuntu-latest
    timeout-minutes: 180  # 3 hours

    strategy:
      matrix:
        model:
          - 'llama3.2:3b'
          - 'qwen2.5-coder:7b'
          - 'deepseek-coder-v2:16b'

    services:
      ollama:
        image: ollama/ollama:latest
        ports:
          - 11434:11434

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install matric-eval
        run: |
          uv venv
          source .venv/bin/activate
          uv pip install -e .

      - name: Pull model
        run: |
          docker exec ${{ job.services.ollama.id }} ollama pull ${{ matrix.model }}

      - name: Run full evaluation
        env:
          MATRIC_EVAL_OLLAMA_URL: http://localhost:11434
        run: |
          source .venv/bin/activate
          matric-eval --tier full --model ${{ matrix.model }} --format json --output results/full-${{ matrix.model }}.json

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: nightly-results-${{ matrix.model }}
          path: results/
          retention-days: 365

      - name: Compare with baseline
        run: |
          source .venv/bin/activate
          python scripts/compare_baseline.py results/full-${{ matrix.model }}.json

      - name: Post results to issue
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: 'Nightly evaluation failed for ${{ matrix.model }}',
              body: 'Full evaluation failed. Check workflow logs for details.',
              labels: ['ci', 'regression']
            })
```

**Nightly Metrics Tracked**:
- Pass rates per benchmark
- Performance trends over time
- New model support validation
- Resource usage patterns

## Quality Gates Summary

### Pull Request Gates (Must Pass to Merge)

| Gate | Tool | Threshold | Blocking |
|------|------|-----------|----------|
| Linting | ruff check | 0 errors | Yes |
| Formatting | ruff format | Properly formatted | Yes |
| Type Checking | mypy | 0 errors | Yes |
| Unit Tests | pytest | 100% pass | Yes |
| Coverage | pytest-cov | >= 80% | Yes |
| Smoke Tests | matric-eval | Pass with llama3.2:3b | Yes |

### Post-Merge Gates (Advisory)

| Gate | Tool | Threshold | Blocking |
|------|------|-----------|----------|
| Security Audit | pip-audit | No critical CVEs | No (warn) |
| SBOM Generation | cyclonedx-py | Valid JSON | No |
| Quick Eval | matric-eval | Within 5% baseline | No (warn) |
| Integration Tests | pytest | 100% pass | No (warn) |

### Release Gates (Must Pass to Publish)

| Gate | Tool | Threshold | Blocking |
|------|------|-----------|----------|
| Version Match | script | Tag == pyproject.toml | Yes |
| Test PyPI Install | pip | Successful install | Yes |
| Package Build | build | Valid wheel & sdist | Yes |
| Full Eval | matric-eval | >= 75% baseline | Yes |

## Environment Configuration

### CI Environment Variables

**Global Secrets** (stored in Gitea Settings):
```bash
PYPI_TOKEN              # PyPI API token for publishing
TEST_PYPI_TOKEN         # Test PyPI token
NPM_TOKEN               # npm registry token
CODECOV_TOKEN           # Codecov upload token
```

**Workflow Variables**:
```yaml
env:
  MATRIC_EVAL_OLLAMA_URL: http://localhost:11434
  MATRIC_EVAL_LOG_LEVEL: INFO
  MATRIC_EVAL_CACHE_DIR: /tmp/matric-eval-cache
  MATRIC_EVAL_RESULTS_DIR: ./results
  PYTHON_VERSION: '3.11'
  NODE_VERSION: '20'
```

### Runner Requirements

**System Resources**:
- CPU: 4 cores minimum
- RAM: 8GB minimum (16GB for full eval)
- Disk: 50GB free space
- Network: Access to ollama registry, PyPI, npm

**Software Prerequisites**:
- Docker (for Ollama service)
- Python 3.11+
- Node.js 20+
- Git
- curl, jq

## Artifact Management

### Artifact Retention Policy

| Artifact Type | Retention | Lifecycle |
|---------------|-----------|-----------|
| Unit Test Results | 30 days | Delete after merge |
| Smoke Test Results | 90 days | Keep for regression |
| Quick Eval Results | 90 days | Keep for regression |
| Full Eval Results | 365 days | Archive yearly |
| Build Packages | 30 days | Delete after release |
| SBOM | 365 days | Archive yearly |
| Security Scans | 90 days | Keep for audit |
| Release Artifacts | Indefinite | Never delete |

### Artifact Storage Structure

```
artifacts/
├── builds/
│   ├── {commit-sha}/
│   │   ├── matric_eval-{version}.whl
│   │   ├── matric_eval-{version}.tar.gz
│   │   └── matric-eval-{version}.tgz
├── test-results/
│   ├── {run-id}/
│   │   ├── unit/
│   │   ├── smoke/
│   │   ├── quick/
│   │   └── integration/
├── security/
│   ├── {date}/
│   │   ├── audit-report.json
│   │   ├── sbom.json
│   │   └── gitleaks-report.json
└── releases/
    └── v{version}/
        ├── packages/
        ├── checksums.txt
        └── release-notes.md
```

## Caching Strategy

### Dependency Caching

**Python Dependencies**:
```yaml
- name: Cache Python dependencies
  uses: actions/cache@v3
  with:
    path: |
      ~/.cache/pip
      ~/.cache/uv
    key: ${{ runner.os }}-python-${{ hashFiles('pyproject.toml', 'uv.lock') }}
    restore-keys: |
      ${{ runner.os }}-python-
```

**Node.js Dependencies**:
```yaml
- name: Cache Node modules
  uses: actions/cache@v3
  with:
    path: ~/.npm
    key: ${{ runner.os }}-node-${{ hashFiles('bindings/typescript/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

**Ollama Models**:
```yaml
- name: Cache Ollama models
  uses: actions/cache@v3
  with:
    path: ~/.ollama
    key: ollama-models-${{ hashFiles('models.txt') }}
```

### Cache Invalidation

**Trigger Cache Refresh**:
- Dependency file changes (pyproject.toml, package.json)
- Weekly scheduled refresh
- Manual workflow dispatch with `clear-cache` input

## Notification Strategy

### Success Notifications

**On Successful Release**:
- Gitea release created with notes
- Team chat notification (optional)
- Email to maintainers (optional)

### Failure Notifications

**On PR Failure**:
- Comment on PR with failure details
- Link to failing workflow run
- Suggested fixes (if automated)

**On Main Branch Failure**:
- Create high-priority issue
- Notify maintainers immediately
- Block subsequent releases

**On Nightly Failure**:
- Create issue with `regression` label
- Weekly summary report

### Notification Channels

```yaml
# .gitea/workflows/notify.yml (webhook integration)
- name: Send notification
  if: failure()
  run: |
    curl -X POST https://chat.integrolabs.net/webhook \
      -H "Content-Type: application/json" \
      -d '{
        "text": "Pipeline failed: ${{ github.workflow }}",
        "link": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
      }'
```

## Performance Optimization

### Pipeline Speed Improvements

**Parallel Execution**:
- Run lint and type-check concurrently
- Matrix builds for multi-version testing
- Parallel benchmark execution

**Job Timeouts**:
- Lint: 5 minutes
- Unit tests: 10 minutes
- Smoke tests: 5 minutes
- Quick eval: 30 minutes
- Full eval: 180 minutes

**Resource Allocation**:
```yaml
jobs:
  quick-job:
    runs-on: ubuntu-latest
    resources:
      cpu: 2
      memory: 4GB

  heavy-job:
    runs-on: ubuntu-latest
    resources:
      cpu: 8
      memory: 16GB
```

### Build Optimization

**Docker Layer Caching**:
```yaml
- name: Build with cache
  uses: docker/build-push-action@v4
  with:
    context: .
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

**Incremental Builds**:
```yaml
- name: Restore build cache
  uses: actions/cache@v3
  with:
    path: |
      build/
      .mypy_cache/
      .pytest_cache/
    key: build-${{ github.sha }}
    restore-keys: |
      build-
```

## Troubleshooting

### Common Pipeline Failures

**Issue**: Ollama service not ready
**Solution**:
```yaml
- name: Wait for Ollama with timeout
  run: |
    timeout 120 bash -c 'until curl -sf http://localhost:11434/api/tags; do
      echo "Waiting for Ollama..."
      sleep 5
    done'
```

**Issue**: Model pull timeout
**Solution**:
```yaml
- name: Pull model with retry
  uses: nick-invision/retry@v2
  with:
    timeout_minutes: 10
    max_attempts: 3
    command: docker exec ${{ job.services.ollama.id }} ollama pull llama3.2:3b
```

**Issue**: Coverage gate fails intermittently
**Solution**:
```yaml
- name: Run tests with coverage
  run: |
    pytest --cov --cov-report=xml --cov-report=term
    # Allow 1% variance for flaky tests
    coverage report --fail-under=79
```

**Issue**: TypeScript build fails after Python changes
**Solution**:
```yaml
- name: Rebuild TypeScript bindings
  run: |
    cd bindings/typescript
    rm -rf dist node_modules
    npm ci
    npm run build
```

### Debug Mode

**Enable Verbose Logging**:
```yaml
- name: Run with debug logging
  env:
    ACTIONS_STEP_DEBUG: true
    MATRIC_EVAL_LOG_LEVEL: DEBUG
  run: |
    matric-eval --tier smoke --model llama3.2:3b --verbose
```

**SSH into Runner** (for debugging):
```yaml
- name: Setup tmate session
  if: failure()
  uses: mxschmitt/action-tmate@v3
  timeout-minutes: 30
```

## Maintenance

### Weekly Tasks

- [ ] Review failed nightly evaluations
- [ ] Check dependency updates
- [ ] Review security scan results
- [ ] Clean old artifacts

### Monthly Tasks

- [ ] Update baseline benchmarks
- [ ] Review pipeline performance metrics
- [ ] Update documentation
- [ ] Audit access tokens and secrets

### Quarterly Tasks

- [ ] Major dependency upgrades
- [ ] Pipeline architecture review
- [ ] Cost optimization review
- [ ] Disaster recovery test

## Metrics and Monitoring

### Pipeline Metrics

**Tracked Metrics**:
- Average pipeline duration
- Success rate per stage
- Cache hit rate
- Artifact storage usage
- Runner utilization

**Dashboards**:
- Gitea Actions insights
- Custom metrics dashboard (Grafana)
- Cost tracking (if applicable)

### Quality Metrics

**Code Quality**:
- Test coverage trend
- Type coverage percentage
- Linting violation count
- Cyclomatic complexity

**Evaluation Metrics**:
- Pass rate trends
- Performance benchmarks
- Model compatibility matrix
- Regression count

## Future Enhancements

### Phase 2

- [ ] Matrix testing across multiple OS (macOS, Windows)
- [ ] GPU runner support for heavy models
- [ ] Distributed evaluation across runners
- [ ] Automated dependency updates (Dependabot)

### Phase 3

- [ ] Performance regression detection
- [ ] Automated changelogs from commits
- [ ] Preview deployments for PRs
- [ ] A/B testing framework

## References

- [Gitea Actions Documentation](https://docs.gitea.io/en-us/actions/)
- [GitHub Actions Reference](https://docs.github.com/en/actions)
- [Python Packaging Guide](https://packaging.python.org/)
- [Semantic Release](https://semantic-release.gitbook.io/)
- [PLANNING.md](../../PLANNING.md) - Project architecture
- [deployment-plan.md](./deployment-plan.md) - Deployment strategy
