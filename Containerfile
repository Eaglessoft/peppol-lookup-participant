FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_CONTEXT_PATH=/ \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO

WORKDIR /opt/app

COPY pyproject.toml README.md ./
COPY app ./app
COPY embed ./embed
COPY scripts/runtime-entrypoint.sh /usr/local/bin/runtime-entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod +x /usr/local/bin/runtime-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/runtime-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

