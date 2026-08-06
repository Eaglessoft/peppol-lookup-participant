#!/bin/sh
set -eu

if [ "${1:-}" = "uvicorn" ]; then
  LOG_CONFIG_PATH="${UVICORN_LOG_CONFIG:-/tmp/uvicorn-log-config.json}"
  export UVICORN_LOG_CONFIG="$LOG_CONFIG_PATH"

  python -m app.shared.uvicorn_logging

  has_log_config=false
  for arg in "$@"; do
    if [ "$arg" = "--log-config" ]; then
      has_log_config=true
      break
    fi
  done

  if [ "$has_log_config" = "false" ]; then
    set -- "$@" --log-config "$LOG_CONFIG_PATH"
  fi
fi

exec "$@"
