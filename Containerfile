FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_CONTEXT_PATH=/ \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO

WORKDIR /opt/app

COPY pyproject.toml README.md ./
COPY app ./app
COPY data/codelists ./data/codelists
COPY embed ./embed
COPY scripts/runtime-entrypoint.sh /usr/local/bin/runtime-entrypoint.sh

RUN pip install --no-cache-dir . \
    && sed -i 's/\r$//' /usr/local/bin/runtime-entrypoint.sh \
    && chmod +x /usr/local/bin/runtime-entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; p=os.environ.get('APP_CONTEXT_PATH', '').strip().rstrip('/'); p='' if p == '/' else p; urllib.request.urlopen(f'http://127.0.0.1:8080{p}/health', timeout=3).read()"

ENTRYPOINT ["/usr/local/bin/runtime-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

