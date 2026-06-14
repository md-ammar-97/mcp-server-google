# Google MCP Server

A lightweight Python server that exposes Google Docs and Gmail as HTTP endpoints.
Send markdown-formatted content and it renders as properly styled Docs headings/bullets and professional HTML emails — not plain text walls.

**Live deployment:** `https://mcp-server-google-695514226672.europe-west1.run.app`

## Features

- `POST /append_to_doc` — append formatted content to any Google Doc
- `POST /create_email_draft` — create a styled HTML Gmail draft
- `POST /send_email` - send a styled HTML Gmail message
- Markdown rendering: headings, bold, italic, bullet lists, dividers
- Operator approval gate before every Google API call (or auto-approve for pipelines)
- Optional API key authentication via `X-Api-Key` request header
- Deployed on Google Cloud Run — continuous deployment from GitHub via Cloud Build

---

## Markdown Syntax

Both endpoints accept markdown in their text fields:

| Syntax | Output |
|---|---|
| `# H1` / `## H2` / `### H3` | Docs: named heading style · Email: `<h1>`–`<h3>` |
| `- item` or `* item` | Docs: bulleted list · Email: `<ul><li>` |
| `**bold**` | Bold |
| `*italic*` or `_italic_` | Italic |
| `***bold+italic***` | Bold + italic |
| `---` | Docs: spacing paragraph · Email: `<hr>` divider |

---

## Quick Start (Local)

### 1. Google Cloud setup

1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services → Library**
2. Enable **Google Docs API** and **Gmail API**
3. Go to **Credentials → Create Credentials → OAuth 2.0 Client ID**
4. Application type: **Desktop app** → Download JSON → save as `credentials.json` in the project root
5. Add your Google account as a test user under **OAuth consent screen → Test users**

### 2. Install and run

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt

cp .env.example .env          # edit .env if needed

uvicorn server:app --reload
```

On first run the browser opens for OAuth. After approving, `token.json` is saved and reused.

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SERVER_API_KEY` | *(unset)* | Server-side secret. When set, all endpoints require the HTTP header `X-Api-Key: <value>` |
| `APPROVAL_MODE` | `terminal` | `terminal` = operator prompt in TTY; `auto` = approve all (required on Cloud Run) |
| `GOOGLE_CREDENTIALS_PATH` | `credentials.json` | Path to OAuth client credentials (local dev) |
| `GOOGLE_TOKEN_PATH` | `token.json` | Path to cached OAuth token (local dev) |
| `GOOGLE_CREDENTIALS_JSON` | *(unset)* | Raw JSON content of `credentials.json` — injected by Cloud Run from Secret Manager |
| `GOOGLE_TOKEN_JSON` | *(unset)* | Raw JSON content of `token.json` — injected by Cloud Run from Secret Manager |
| `PORT` | `8000` | HTTP listen port — Cloud Run injects this automatically |

> **`SERVER_API_KEY` vs `X-Api-Key`:** `SERVER_API_KEY` is the environment variable the server reads. `X-Api-Key` is the HTTP request header clients must send. They are not the same thing — do not add `X-API-KEY` as an env var.

Copy `.env.example` to `.env` and fill in values for local development.

---

## API Reference

All mutating endpoints require `X-Api-Key` when `SERVER_API_KEY` is set.

### Append to a Google Doc

```bash
SERVICE_URL="https://mcp-server-google-695514226672.europe-west1.run.app"
API_KEY="PASTE_YOUR_API_KEY_HERE"

cat > payload.json <<'EOF'
{"doc_id":"YOUR_GOOGLE_DOC_ID","content":"# Section\n\n**Key point:** something important.\n\n- Item one\n- Item two"}
EOF

curl -i -X POST "$SERVICE_URL/append_to_doc" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  --data-binary @payload.json
```

```json
{"status": "ok", "doc_id": "YOUR_DOC_ID", "chars_added": 58}
```

`doc_id` comes from your Doc URL: `https://docs.google.com/document/d/{doc_id}/edit`

### Create a Gmail draft

```bash
SERVICE_URL="https://mcp-server-google-695514226672.europe-west1.run.app"
API_KEY="PASTE_YOUR_API_KEY_HERE"

cat > payload.json <<'EOF'
{"to":"recipient@example.com","subject":"Project Update","body":"# Project Update\n\n**Status:** On track\n\n- Milestone A complete\n- Milestone B in progress\n\n*Regards*"}
EOF

curl -i -X POST "$SERVICE_URL/create_email_draft" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  --data-binary @payload.json
```

```json
{"status": "ok", "draft_id": "r12345abc"}
```

The draft appears in Gmail → Drafts with full HTML formatting (600 px card, proper heading hierarchy, bullet lists).

### Send a Gmail message

Use the same payload as draft creation, but call the send endpoint:

```bash
curl -i -X POST "$SERVICE_URL/send_email" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  --data-binary @payload.json
```

```json
{"status": "ok", "message_id": "18f...", "thread_id": "18f..."}
```

### Health check (no auth required)

```bash
curl https://mcp-server-google-695514226672.europe-west1.run.app/health
# → {"status":"ok"}
```

Interactive docs: `http://localhost:8000/docs` (local only)

---

## Docker

```bash
# Pre-generate token.json on a machine with a browser (one-time)
python -c "from auth import get_credentials; get_credentials()"

# Build
docker build -t google-mcp-server .

# Run — mount credentials at runtime, never bake them into the image
docker run -d \
  --name google-mcp-server \
  -p 8000:8000 \
  -e SERVER_API_KEY=your-secret-key \
  -e APPROVAL_MODE=auto \
  -e GOOGLE_CREDENTIALS_PATH=/secrets/credentials.json \
  -e GOOGLE_TOKEN_PATH=/secrets/token.json \
  -v /path/to/credentials.json:/secrets/credentials.json:ro \
  -v /path/to/token.json:/secrets/token.json \
  google-mcp-server
```

---

## Deploy to Cloud Run

The service is live and continuously deployed via Cloud Run's built-in GitHub integration.

| Detail | Value |
|---|---|
| Project | NextLeap (`gen-lang-client-0491576843`) |
| Service | `mcp-server-google` |
| Region | `europe-west1` |
| URL | `https://mcp-server-google-695514226672.europe-west1.run.app` |
| Deployment | Cloud Run built-in CD: push to `main` → Cloud Build → Cloud Run |
| Auth | Allow unauthenticated at Cloud Run level; app enforces `X-Api-Key` on mutating endpoints |

### How it works

1. Push to `main` → Cloud Build triggers automatically
2. Cloud Build builds the Docker image and pushes it to Artifact Registry (managed automatically)
3. Cloud Run deploys the new revision
4. At startup, `start.sh` writes `GOOGLE_CREDENTIALS_JSON` and `GOOGLE_TOKEN_JSON` (from Secret Manager) to `/tmp`, sets path env vars, then starts uvicorn

### Cloud Run environment

| Variable | Source | Value |
|---|---|---|
| `APPROVAL_MODE` | Plain env var | `auto` |
| `GOOGLE_CREDENTIALS_JSON` | Secret Manager: `google-mcp-credentials:latest` | Raw `credentials.json` content |
| `GOOGLE_TOKEN_JSON` | Secret Manager: `google-mcp-token:latest` | Raw `token.json` content |
| `SERVER_API_KEY` | Secret Manager: `google-mcp-api-key:latest` | Backend API key |

For the full setup guide, API key rotation, log commands, and troubleshooting see [`deployment_plan.md`](deployment_plan.md).

---

## Security

| File | Purpose | Committed? |
|---|---|---|
| `credentials.json` | OAuth 2.0 client secret | No — `.gitignore` |
| `token.json` | Cached user OAuth token | No — `.gitignore` |
| `.env` | Local secrets | No — `.gitignore` |

- `SERVER_API_KEY` is stored in Google Secret Manager in production — never in code or committed files
- `APPROVAL_MODE=terminal` is the safe default locally — requires explicit `y` before any Google API call
- Cloud Run provides managed TLS on `*.run.app` automatically
- No GitHub Actions, no `GCP_SA_KEY` / `GCP_PROJECT_ID` secrets needed in GitHub
