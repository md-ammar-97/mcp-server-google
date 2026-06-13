#!/bin/sh
set -e

# Credential injection at startup — three modes:
#
#   1. GOOGLE_CREDENTIALS_JSON / GOOGLE_TOKEN_JSON (raw JSON strings)
#      Used by Cloud Run when secrets are linked from Secret Manager.
#
#   2. GOOGLE_CREDENTIALS_B64 / GOOGLE_TOKEN_B64 (base64-encoded JSON)
#      Used for plain Docker and local testing.
#
#   3. Neither set — falls back to file paths in GOOGLE_CREDENTIALS_PATH /
#      GOOGLE_TOKEN_PATH for local development with files on disk.

if [ -n "$GOOGLE_CREDENTIALS_JSON" ]; then
  printf '%s' "$GOOGLE_CREDENTIALS_JSON" > /tmp/credentials.json
  export GOOGLE_CREDENTIALS_PATH=/tmp/credentials.json
elif [ -n "$GOOGLE_CREDENTIALS_B64" ]; then
  printf '%s' "$GOOGLE_CREDENTIALS_B64" | base64 -d > /tmp/credentials.json
  export GOOGLE_CREDENTIALS_PATH=/tmp/credentials.json
fi

if [ -n "$GOOGLE_TOKEN_JSON" ]; then
  printf '%s' "$GOOGLE_TOKEN_JSON" > /tmp/token.json
  export GOOGLE_TOKEN_PATH=/tmp/token.json
elif [ -n "$GOOGLE_TOKEN_B64" ]; then
  printf '%s' "$GOOGLE_TOKEN_B64" | base64 -d > /tmp/token.json
  export GOOGLE_TOKEN_PATH=/tmp/token.json
fi

exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"
