# Contributing to membase

Thank you for your interest in contributing to membase. This document
covers the setup, conventions, and workflow for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions.

## Prerequisites

- Python 3.9+
- Git
- A [Hugging Face account](https://huggingface.co/join) with an API token
  (for running integration tests)

## Development Setup

```bash
# Clone the repository
git clone https://github.com/jrolf/membase.git
cd membase

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all unit tests
pytest

# Run with verbose output
pytest -v
```

Unit tests do not require network access or an HF token. They cover
formatting, error classes, search logic, and compatibility helpers.

## Linting

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix what can be fixed
ruff check src/ tests/ --fix
```

## Branch Model

- **`main`** — production. Pushes here trigger PyPI publishing.
- **`develop`** — integration branch. All work targets `develop` first.
- **Feature branches** — branch from `develop`, merge back into `develop`.

Branch naming:

- `feature/description` — new functionality
- `fix/description` — bug fixes
- `docs/description` — documentation changes

## Commit Messages

Use concise, descriptive commit messages. Focus on *why*, not *what*.

```
Add parallel read support to grep

Search was bottlenecked by sequential HTTP reads. Using
ThreadPoolExecutor with 16 workers achieves ~16x speedup.
```

## Pull Request Process

1. Branch from `develop`.
2. Make your changes. Add or update tests if behavior changes.
3. Run `pytest` and `ruff check` — both must pass.
4. Update `CHANGELOG.md` under the `[Unreleased]` section.
5. Open a PR targeting `develop`.

## Coding Standards

- **Readability first.** Clear, explicit code over clever one-liners.
- **Docstrings required** on all public functions and classes.
- **No type hints** unless necessary for tooling integration.
- **No new dependencies** without discussion. The library has one
  mandatory dependency (`huggingface_hub`) and that's intentional.
- **Short method names.** Token efficiency is a design constraint.

## Release Process

1. Merge `develop` into `main`.
2. Bump the version in `pyproject.toml` and `src/membase/__init__.py`.
3. Add a dated entry to `CHANGELOG.md`.
4. Push to `main` — GitHub Actions handles PyPI publishing automatically.

## Questions?

Open an issue or reach out at james@think.dev.
