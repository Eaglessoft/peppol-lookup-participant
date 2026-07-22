# Peppol Lookup API

Python FastAPI service for PEPPOL participant lookup, company-to-participant discovery,
source diagnostics, and codelist-backed validation.

## Features

- FastAPI application with `/api`, `/health`, and versioned lookup routes.
- Participant lookup across Directory, SML/SMK, SMP, and OpenPeppol Lookup adapters.
- Company discovery with Peppol participant scheme candidate generation and validation.
- Local codelist cache refresh from OpenPeppol eDelivery JSON artifacts.
- Source-level status, TTL caching, local rate limiting, and diagnostics.
- Shared settings, logging, CORS, response helpers, and schemas.
- Embed package with standalone widget files and usage documentation.
- Container, Docker Compose, VS Code, Dev Container, and test scaffolding.

## Requirements

- Python 3.12+
- Docker, optional

## Local Development

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

The committed defaults point to the public Peppol production and test discovery
services. The repository includes a codelist cache in `data/codelists`, so no
Peppol-specific environment variables are required for a normal local run.

## Docker

```bash
docker build -t eaglessoftbv/peppol-lookup-participant -f Containerfile .
docker run --rm -p 8080:8080 eaglessoftbv/peppol-lookup-participant
```

Or with Compose:

```bash
docker compose -f infra/docker-compose.yml up --build
```

## Access URLs

- API info: `http://localhost:8080/api`
- Health: `http://localhost:8080/health`
- Sources: `http://localhost:8080/api/v1/sources`
- Source health: `http://localhost:8080/api/v1/sources/health?check=true`
- Participant lookup: `http://localhost:8080/api/v1/participants/0192:987654321?mode=detail&sources=directory,sml`
- Company lookup: `http://localhost:8080/api/v1/companies?country=BE&identifier=0123456749&identifier_type=0208&mode=detail`
- Participant countries: `http://localhost:8080/api/v1/codelists/participant-countries`
- Embed sample: `http://localhost:8080/embed/sample.html`
- Embed JavaScript: `http://localhost:8080/embed/embed.js`
- Embed CSS: `http://localhost:8080/embed/embed.css`

For website integration, serve `embed.js` and `embed.css` from the same hosted
service or from the website CDN, then point the widget to the deployed API URL:

```html
<peppol-lookup api-url="https://api.example.com"></peppol-lookup>
<link rel="stylesheet" href="https://api.example.com/embed/embed.css">
<script src="https://api.example.com/embed/embed.js" defer></script>
```

## Environment Variables

- `APP_CONTEXT_PATH` (default: `/`)
  Application context path when the service is exposed behind a path prefix.
- `LOG_FORMAT` (default: `json`)
  Supported values: `json`, `plain`.
- `LOG_LEVEL` (default: `INFO`)
  Examples: `DEBUG`, `INFO`, `WARN`, `ERROR`.
- `ALLOWED_ORIGINS` (default: `*`)
  CORS allowlist, comma-separated. For a public website, set this to the real
  website origin instead of `*`.
- `JSON_PRETTY_PRINT` (default: `false`)
  If `true`, API JSON responses are returned in pretty format.
- `PEPPOL_RATE_LIMIT_REQUESTS` / `PEPPOL_RATE_LIMIT_WINDOW_SECONDS`
  Local per-client rate limit settings.
- `PEPPOL_CODELIST_REQUIRED` (default: `true`)
  Requires a valid local codelist cache at startup.
- `PEPPOL_CODELIST_CACHE_DIR` (default: `data/codelists`)
  Local codelist cache directory.
- `PEPPOL_SML_PROD_DNS_ZONE` (default: `participant.sml.prod.tech.peppol.org`)
  Production SML DNS zone used for participant DNS resolution.
- `PEPPOL_SML_TEST_DNS_ZONE` (default: `participant.sml.test.tech.peppol.org`)
  Test SMKv2 DNS zone used for participant DNS resolution.

## Example Runtime Configurations

JSON logs with root context:

```bash
docker run --rm -p 8080:8080 \
  -e LOG_FORMAT=json \
  -e LOG_LEVEL=INFO \
  eaglessoftbv/peppol-lookup-participant
```


```bash
docker run --rm -p 8080:8080 \
  -e ALLOWED_ORIGINS=https://tools.example.com \
  eaglessoftbv/peppol-lookup-participant
```

## Release Image Workflow

`.github/workflows/container-build.yml` builds and pushes the release image when
a GitHub release is published. It tags the Docker image with the release tag,
`sha-<commit>`, and `latest`, using the same Docker Hub secret names as the
existing Eaglessoft service repositories.

`PEPPOL_CODELIST_REQUIRED=true` requires a valid local codelist cache at startup. The
repository includes cached codelist data under `data/codelists`; set
`PEPPOL_CODELIST_REQUIRED=false` only for local fallback/testing scenarios.

SMP URLs are not configured manually. The service resolves the responsible SMP
from the configured production SML or test SMK DNS zone for each participant.
Production defaults to `participant.sml.prod.tech.peppol.org`; test defaults to
`participant.sml.test.tech.peppol.org`, which is used by the public Peppol TEST
Directory. If your test participant is published to a different acceptance/test
SMK, override `PEPPOL_SML_TEST_DNS_ZONE`.

Refresh codelists:

```bash
curl -X POST http://localhost:8080/api/v1/codelists/refresh
```


## Documentation

- Development setup: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)
- Technical overview: [`docs/TECHNICAL_OVERVIEW.md`](docs/TECHNICAL_OVERVIEW.md)
- Peppol lookup service design: [`docs/PEPPOL_LOOKUP_SERVICE.md`](docs/PEPPOL_LOOKUP_SERVICE.md)
- Embed usage: [`docs/EMBED_USAGE.md`](docs/EMBED_USAGE.md)
- Contributing rules: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)
