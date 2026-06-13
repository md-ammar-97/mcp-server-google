# Google MCP Server

A lightweight Python server that exposes Google Docs and Gmail as HTTP endpoints.
Send markdown-formatted content and it renders as properly styled Docs headings/bullets and professional HTML emails — not plain text walls.

## Features

- `POST /append_to_doc` — append formatted content to any Google Doc
- `POST /create_email_draft` — create a styled HTML Gmail draft
- Markdown rendering: headings, bold, italic, bullet lists, dividers
- Operator approval gate before every Google API call (or auto-approve for pipelines)
- Optional API key authentication
- Docker + Railway ready (credentials injected via env vars — never baked into image)

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
| `SERVER_API_KEY` | *(unset)* | If set, all endpoints require `X-API-Key: <value>` |
| `APPROVAL_MODE` | `terminal` | `terminal` = operator prompt in TTY; `auto` = approve all |
| `GOOGLE_CREDENTIALS_PATH` | `credentials.json` | Path to OAuth client credentials |
| `GOOGLE_TOKEN_PATH` | `token.json` | Path to cached OAuth token |
| `PORT` | `8000` | HTTP listen port |

Copy `.env.example` to `.env` and fill in values.

---

## API Reference

All mutating endpoints require `X-API-Key` when `SERVER_API_KEY` is set.

### Append to a Google Doc

```bash
curl -X POST http://localhost:8000/append_to_doc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "doc_id": "YOUR_DOC_ID",
    "content": "# Section\n\n**Key point:** something important.\n\n- Item one\n- Item two"
  }'
```

```json
{"status": "ok", "doc_id": "YOUR_DOC_ID", "chars_added": 58}
```

`doc_id` comes from your Doc URL: `https://docs.google.com/document/d/{doc_id}/edit`

### Create a Gmail draft

```bash
curl -X POST http://localhost:8000/create_email_draft \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "to": "recipient@example.com",
    "subject": "Project Update",
    "body": "# Project Update\n\n**Status:** On track\n\n- Milestone A complete\n- Milestone B in progress\n\n*Regards*"
  }'
```

```json
{"status": "ok", "draft_id": "r12345abc"}
```

The draft appears in Gmail → Drafts with full HTML formatting (600 px card, proper heading hierarchy, bullet lists).

### Health check

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

Interactive docs: `http://localhost:8000/docs`

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

## Deploy to Railway

Railway builds from the Dockerfile and gives you a public HTTPS URL. Credentials are passed as base64-encoded environment variables and decoded to `/tmp` at startup by `start.sh`.

### 1. Encode credentials (run locally in PowerShell)

```powershell
$creds = [Convert]::ToBase64String([IO.File]::ReadAllBytes("credentials.json"))
$token = [Convert]::ToBase64String([IO.File]::ReadAllBytes("token.json"))
Write-Host "GOOGLE_CREDENTIALS_B64=$creds"
Write-Host "GOOGLE_TOKEN_B64=$token"
```

### 2. Deploy

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo** → select this repo
3. Railway detects the `Dockerfile` automatically

### 3. Set environment variables in Railway dashboard

| Variable | Value |
|---|---|
| `SERVER_API_KEY` | Strong random string |
| `APPROVAL_MODE` | `auto` |
| `GOOGLE_CREDENTIALS_B64` | Value from step 1 |
| `GOOGLE_TOKEN_B64` | Value from step 1 |

> Do **not** set `PORT` — Railway injects it automatically.

### 4. Generate a public domain

Railway dashboard → **your service → Settings → Networking → Generate Domain**

```bash
curl https://your-app.up.railway.app/health
# → {"status":"ok"}
```

For full deployment options (local dev, Docker, VPS/systemd, Railway) see [`deployment_plan.md`](deployment_plan.md).

---

## Security

| File | Purpose | Committed? |
|---|---|---|
| `credentials.json` | OAuth 2.0 client secret | No — `.gitignore` |
| `token.json` | Cached user OAuth token | No — `.gitignore` |
| `.env` | Runtime secrets | No — `.gitignore` |

- Set `SERVER_API_KEY` to a strong random value in production
- Keep `APPROVAL_MODE=terminal` when running locally — it requires explicit `y` before any Google API call
- HTTPS is provided automatically by Railway; for VPS use nginx + Let's Encrypt
