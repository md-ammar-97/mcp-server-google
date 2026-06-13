# Google MCP Server — Deployment Plan

## Overview

This server exposes two Google API actions over HTTP:
- `POST /append_to_doc` — append formatted text to a Google Doc
- `POST /create_email_draft` — create a styled HTML Gmail draft

All mutating endpoints require operator approval (configurable) and optionally an API key.

---

## Markdown Formatting Support

Both endpoints accept markdown syntax in their text/body fields and render it professionally.

### Supported syntax

| Syntax | Google Doc result | Email result |
|---|---|---|
| `# Heading` / `## Heading` / `### Heading` | Heading 1 / 2 / 3 named style | `<h1>` / `<h2>` / `<h3>` with size + weight |
| `- item` or `* item` | Bulleted list | `<ul><li>` list |
| `**bold**` | Bold text | `<strong>` |
| `*italic*` or `_italic_` | Italic text | `<em>` |
| `***bold+italic***` | Bold + italic | `<strong><em>` |
| `---` | Empty spacing paragraph | `<hr>` divider |

### Example content string

```
# Quarterly Update

**Status:** On track

## Highlights
- Feature A shipped
- Bug #142 fixed

*Thank you for your continued support.*
```

Gmail drafts are sent as `multipart/alternative` (plain text + styled HTML card), so they render correctly in all email clients.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Or Docker (see below) |
| Google Cloud project | Console: https://console.cloud.google.com |
| Google Docs API enabled | APIs & Services → Enable APIs |
| Gmail API enabled | APIs & Services → Enable APIs |
| OAuth 2.0 Client ID | Type: Desktop App → download as `credentials.json` |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SERVER_API_KEY` | *(unset)* | If set, all non-health endpoints require `X-API-Key: <value>` |
| `APPROVAL_MODE` | `terminal` | `terminal` = operator prompt; `auto` = approve all (trusted pipelines only) |
| `GOOGLE_CREDENTIALS_PATH` | `credentials.json` | Path to OAuth 2.0 client credentials file |
| `GOOGLE_TOKEN_PATH` | `token.json` | Path to cached OAuth token file |
| `PORT` | `8000` | HTTP listen port |

Copy `.env.example` to `.env` and fill in values before running.

---

## Option A: Local Development

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Place credentials.json in the project directory
#    (downloaded from Google Cloud Console)

# 4. First-run OAuth: opens browser, saves token.json
uvicorn server:app --reload

# 5. Confirm server is up
curl http://localhost:8000/health
# → {"status":"ok"}
```

On first startup the browser opens for the OAuth consent flow. After approving, `token.json` is written and reused on all subsequent starts.

---

## Option B: Docker Deployment

### Pre-generate token.json (required before running headless)

The OAuth browser flow cannot run inside a headless container. Generate `token.json` once on a machine with a browser:

```bash
# On your local machine (with browser access):
pip install -r requirements.txt
python -c "from auth import get_credentials; get_credentials()"
# → Browser opens, approve access → token.json is created
```

### Build and run

```bash
# Build
docker build -t google-mcp-server .

# Run — mount credentials at their expected paths
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

> **Note:** `token.json` is mounted read-write (no `:ro`) because the auth library rewrites it when the access token is refreshed.

### Health check

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

---

## Option C: VPS / Cloud VM (systemd)

```ini
# /etc/systemd/system/google-mcp-server.service
[Unit]
Description=Google MCP Server
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/google-mcp-server
EnvironmentFile=/opt/google-mcp-server/.env
ExecStart=/opt/google-mcp-server/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now google-mcp-server
sudo systemctl status google-mcp-server
```

### HTTPS via nginx reverse proxy

```nginx
server {
    listen 443 ssl;
    server_name mcp.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/mcp.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.yourdomain.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }
}
```

Obtain a certificate with `certbot --nginx -d mcp.yourdomain.com`.

---

## Option D: GitHub + Railway

Railway builds from the Dockerfile and provides a public HTTPS URL with zero server management. Because `credentials.json` and `token.json` are excluded from git, they are passed in as base64-encoded environment variables and decoded to `/tmp` at container startup by `start.sh`.

### 1. Pre-generate token.json locally (one-time)

The OAuth browser flow must run on a machine with a browser before deploying:

```bash
pip install -r requirements.txt
python -c "from auth import get_credentials; get_credentials()"
# → Browser opens → approve → token.json is written
```

### 2. Encode credentials for Railway

Run this in PowerShell from the project directory:

```powershell
$creds = [Convert]::ToBase64String([IO.File]::ReadAllBytes("credentials.json"))
$token = [Convert]::ToBase64String([IO.File]::ReadAllBytes("token.json"))
Write-Host "GOOGLE_CREDENTIALS_B64=$creds"
Write-Host "GOOGLE_TOKEN_B64=$token"
```

Copy both output lines — you will paste the values into Railway.

### 3. Push to GitHub

```bash
git init
git add .        # .gitignore already excludes credentials.json, token.json, .env
git commit -m "Initial commit"

# Create a private repo and push (requires GitHub CLI)
gh repo create google-mcp-server --private --source=. --push
```

Or create the repo on github.com manually and push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/google-mcp-server.git
git branch -M main
git push -u origin main
```

### 4. Create a Railway project

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Authorise Railway to access your GitHub account if prompted
3. Select **google-mcp-server**
4. Railway detects the `Dockerfile` automatically — no extra config needed

### 5. Set environment variables

In the Railway dashboard: **your service → Variables → Add variable**

| Variable | Value |
|---|---|
| `SERVER_API_KEY` | Strong random string (e.g. `openssl rand -hex 32`) |
| `APPROVAL_MODE` | `auto` |
| `GOOGLE_CREDENTIALS_B64` | Value from step 2 |
| `GOOGLE_TOKEN_B64` | Value from step 2 |

> Do **not** set `PORT` — Railway injects it automatically and `start.sh` reads it.

### 6. Generate a public domain

Railway dashboard → **your service → Settings → Networking → Generate Domain**

### 7. Verify

```bash
curl https://your-app.up.railway.app/health
# → {"status":"ok"}
```

### Notes

| Topic | Detail |
|---|---|
| Token refresh | `token.json` is written to `/tmp` on each start from `GOOGLE_TOKEN_B64`. The embedded refresh token lets Google issue a fresh access token automatically — no manual re-auth needed. |
| Token rotation | If you revoke and re-generate `token.json` locally, re-encode it, update `GOOGLE_TOKEN_B64` in Railway Variables, and trigger a redeploy. |
| Sleep on free tier | Railway free-tier containers sleep after inactivity. `APPROVAL_MODE=auto` prevents terminal prompts from hanging on wake. |
| Cost | The Hobby plan ($5/month) keeps the container always-on. The free tier is fine for occasional use. |

---

## Calling the API

All mutating endpoints require `X-API-Key` if `SERVER_API_KEY` is set.

### Append to a Google Doc

```bash
curl -X POST http://localhost:8000/append_to_doc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "doc_id": "YOUR_DOC_ID",
    "content": "# Section Title\n\nSome **bold** text and *italic* text.\n\n- Point one\n- Point two"
  }'
```

Response:
```json
{"status": "ok", "doc_id": "YOUR_DOC_ID", "chars_added": 72}
```

### Create a Gmail draft

```bash
curl -X POST http://localhost:8000/create_email_draft \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "to": "recipient@example.com",
    "subject": "Project Update",
    "body": "# Project Update\n\n**Status:** On track\n\n- Milestone A complete\n- Milestone B in progress\n\n*Regards*"
  }'
```

Response:
```json
{"status": "ok", "draft_id": "r12345abc"}
```

---

## Credential Management

| File | Purpose | Secret? |
|---|---|---|
| `credentials.json` | OAuth 2.0 Client ID (app identity) | Yes — never commit |
| `token.json` | Cached user OAuth token (access + refresh) | Yes — never commit |

Both files are in `.gitignore`. In Docker/CI environments:
- Use bind mounts or secret management (AWS Secrets Manager, GCP Secret Manager, Vault)
- Set `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_TOKEN_PATH` to the mounted paths
- Store `token.json` in a writable volume so token refreshes persist across container restarts

Token expiry:
- Access tokens expire every hour — the library refreshes them automatically using the refresh token
- Refresh tokens are long-lived but can be revoked from Google Account settings
- If `token.json` is lost or revoked, re-run the OAuth browser flow on a machine with a browser

---

## Security Checklist

- [ ] `SERVER_API_KEY` is set to a strong random string in production
- [ ] `APPROVAL_MODE=auto` is only used for trusted, authenticated callers
- [ ] `credentials.json` and `token.json` are not committed to git
- [ ] HTTPS is configured (TLS termination via nginx or cloud load balancer)
- [ ] Server is not exposed on a public IP without HTTPS + API key
- [ ] File permissions: `chmod 600 credentials.json token.json`
- [ ] Token volume is writable so token refreshes persist

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: credentials.json not found` | Credentials file missing or wrong path | Check `GOOGLE_CREDENTIALS_PATH`; download from Google Cloud Console |
| `401 Unauthorized` on API call | `SERVER_API_KEY` set but header missing | Add `-H "X-API-Key: <key>"` to your request |
| `422 Unprocessable Entity` | Invalid `doc_id` (empty) or bad email address | Check request payload |
| `403 Forbidden: Action rejected by operator` | Operator typed `n` at approval prompt | Re-run and type `y`, or set `APPROVAL_MODE=auto` |
| Token expired / `invalid_grant` | `token.json` is stale or revoked | Delete `token.json`, re-run OAuth browser flow |
| Server hangs waiting for input in Docker | `APPROVAL_MODE` left as `terminal` in headless env | Set `APPROVAL_MODE=auto` in `.env` |
| `google.auth.exceptions.TransportError` | No internet / firewall blocking Google APIs | Check outbound connectivity to `*.googleapis.com` |
