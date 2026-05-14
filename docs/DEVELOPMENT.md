# Development Guide

## Local Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## Test

```bash
pytest
```

## Lint

```bash
ruff check .
```

## VS Code

Shared tasks are defined in `.vscode/tasks.json`.

- `dev_up`: starts Uvicorn with reload.
- `test`: runs pytest.
- `lint`: runs Ruff.

