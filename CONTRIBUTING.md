# Contributing to moltbunker-sdk

Thank you for your interest in contributing!

## Local setup

```bash
pip install -e ".[dev]"
```

## Running tests

```bash
pytest
pytest --cov=moltbunker --cov-report=term-missing
```

## Code style

```bash
ruff check moltbunker/
mypy moltbunker/
```

## Branch conventions

| Prefix | Used for |
|--------|----------|
| SDK-NN | Feature/fix |
| OPS-NN | CI/tooling |
| DOCS-NN | Documentation |

## Opening a pull request

1. Fork & push your branch
2. Open PR against moltbunker/moltbunker-sdk:main
3. Fill in the PR template
4. Ensure CI is green
