# Technical Overview

## Main Folders

- `app/api`
  - HTTP route definitions and versioned API modules.
- `app/shared`
  - Shared settings, logging, response schemas, and embed configuration helpers.
- `embed`
  - Standalone web component assets for external integration.
- `docs`
  - Project documentation.
- `infra`
  - Runtime/deployment examples.
- `scripts`
  - Runtime scripts used by the container image.
- `tests`
  - Pytest test suite.

## Runtime Flow

1. `app.main:create_app` loads settings and configures logging.
2. CORS middleware is configured from environment variables.
3. Shared API routes are mounted.
4. Embed clients call the same public API endpoints.

## Shared Structure

- API shared code lives under `app/shared`.
- Embed-facing shared configuration is represented by `app/shared/embed.py`.
- Browser embed assets live under `embed` and should remain framework-independent.

