# Peppol Lookup API

Python service scaffold for a PEPPOL-related API with shared API helpers, shared embed configuration, documentation, and container-ready runtime structure.

## Features

- FastAPI application with `/api`, `/health`, and shared route structure.
- Shared settings, logging, CORS, response helpers, and schemas.
- Embed package with standalone widget files and usage documentation.
- Container, Docker Compose, VS Code, Dev Container, and test scaffolding.

## Requirements

- Python 3.12+
- Docker, optional

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## Access URLs

- API info: `http://localhost:8080/api`
- Health: `http://localhost:8080/health`
- Embed sample: open `embed/sample.html`

## Documentation

- Development setup: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)
- Technical overview: [`docs/TECHNICAL_OVERVIEW.md`](docs/TECHNICAL_OVERVIEW.md)
- Peppol lookup service design: [`docs/PEPPOL_LOOKUP_SERVICE.md`](docs/PEPPOL_LOOKUP_SERVICE.md)
- Embed usage: [`docs/EMBED_USAGE.md`](docs/EMBED_USAGE.md)
- Contributing rules: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)
