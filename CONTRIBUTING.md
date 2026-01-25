# Contributing to matric-eval

Thank you for your interest in contributing to matric-eval.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/jmagly/matric-eval.git
cd matric-eval

# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -q

# Run tests with coverage
uv run pytest tests/ --cov=src/matric_eval --cov-fail-under=80
```

## Code Style

This project uses:
- **ruff** for linting and formatting
- **mypy** for type checking

Run checks before submitting:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

## Testing

- All new features must include tests
- Maintain minimum 80% code coverage
- Use pytest markers appropriately:
  - `@pytest.mark.unit` - Fast, isolated tests
  - `@pytest.mark.integration` - Tests requiring external services
  - `@pytest.mark.slow` - Tests taking >1s

## Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes with tests
4. Ensure all tests pass and coverage is maintained
5. Submit a pull request

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include reproduction steps for bugs
- Check existing issues before creating new ones

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
