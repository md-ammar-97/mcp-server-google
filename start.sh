#!/bin/sh
set -e

# On Railway/Docker, credentials are supplied as base64 env vars and written to
# /tmp at startup. Falls back to file-based paths for local development.
if [ -n "$GOOGLE_CREDENTIALS_B64" ]; then
  printf '%s' "$GOOGLE_CREDENTIALS_B64" | base64 -d > /tmp/credentials.json
  export GOOGLE_CREDENTIALS_PATH=/tmp/credentials.json
fi

if [ -n "$GOOGLE_TOKEN_B64" ]; then
  printf '%s' "$GOOGLE_TOKEN_B64" | base64 -d > /tmp/token.json
  export GOOGLE_TOKEN_PATH=/tmp/token.json
fi

exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"
