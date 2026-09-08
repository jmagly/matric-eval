# Contributing to matric-eval

Thank you for your interest in contributing to matric-eval.

## Development Setup

```bash
# Clone the repository
git clone https://git.integrolabs.net/roctinam/matric-eval.git
cd matric-eval

# Install dependencies
uv sync --locked --extra dev --extra study

# Run tests
uv run pytest tests/ -q

# Run tests with coverage
make test-coverage-fail
```

The full test suite exercises the official IFEval study scorer, so development
setup includes both `dev` and `study` extras.

## Code Style

This project uses:
- **ruff** for linting and formatting
- **mypy** for type checking

Run checks before submitting:

```bash
make lint
make format-check
make type-check
make test-coverage-fail
```

Run all merge-blocking checks with `make ci`. Gitea Actions and GitHub Actions
invoke these exact targets so local and hosted results have the same semantics.

Strict mypy currently uses `mypy-baseline.json` as a debt ratchet: existing
findings may be removed, but a new finding or an increased count fails
`make type-check`. Use `make type-check-strict` to inspect all findings. Run
`make type-check-update` only when a reviewed change reduces the baseline.

Mainline protection should require the `Quality Gates`, `Test and Coverage`,
`Smoke Tests`, and `Build Package` checks. Do not merge while any required check is pending,
failed, skipped unexpectedly, or absent.

## Testing

- All new features must include tests
- Maintain minimum 80% code coverage
- Use pytest markers appropriately:
  - `@pytest.mark.unit` - Fast, isolated tests
  - `@pytest.mark.integration` - Tests requiring external services
  - `@pytest.mark.slow` - Tests taking >1s

## Pull Requests

1. Use a branch in the canonical Gitea repository, or fork it if you lack write access
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes with tests
4. Ensure all tests pass and coverage is maintained
5. Submit a pull request against Gitea `main`; wait for the required CI checks before merging

## Reporting Issues

- Use the [canonical Gitea tracker](https://git.integrolabs.net/roctinam/matric-eval/issues) for engineering bug reports and feature requests
- Include reproduction steps for bugs
- Check existing issues before creating new ones

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Versioning and Releases

Use CalVer `YYYY.M.PATCH`, with an unpadded month and a counter starting at zero
for each UTC month. Run `make version-check` before review; use `make version-bump`
to update Python, TypeScript and lock versions together. Result/protocol schema
versions are independent and must not be changed by a package bump.

Follow [the release guide](docs/development/releasing.md). Distribution is through
verified Gitea release downloads; PyPI and npm registry publishing are disabled.
