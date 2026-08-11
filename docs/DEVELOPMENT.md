# Development Guide

## Local Run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

The default configuration uses public Peppol Directory, SML, SMK, SMP, and
Lookup Service sources. The codelist cache is committed under `data/codelists`,
so a normal local run does not require setting Peppol-specific environment
variables.

Set `PEPPOL_CODELIST_REQUIRED=false` only when intentionally running without a
valid local codelist cache.

## Test

```bash
PYTHONPYCACHEPREFIX=.cache/python python -m pytest
```

PowerShell:

```powershell
$env:PYTHONPYCACHEPREFIX = ".cache/python"
python -m pytest
```

Pytest, Ruff, and Python bytecode caches are kept under `.cache/`. The shared
VS Code tasks set the bytecode cache location automatically.

## Lint

```bash
PYTHONPYCACHEPREFIX=.cache/python python -m ruff check .
```

## VS Code

Shared tasks are defined in `.vscode/tasks.json`.

- `dev_up`: starts Uvicorn with reload.
- `test`: runs pytest.
- `lint`: runs Ruff.

