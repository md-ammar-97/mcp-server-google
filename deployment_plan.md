# Google MCP Server — Deployment Plan

## Overview

This server exposes three Google API actions over HTTP:
- `POST /append_to_doc` — append formatted text to a Google Doc
- `POST /create_email_draft` — create a styled HTML Gmail draft
- `POST /send_email` — send a styled HTML Gmail message

All mutating endpoints require operator approval (configurable) and optionally an API key.

---

## Markdown Formatting Support

All three content endpoints accept markdown syntax in their text/body fields and render it professionally.

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

Gmail drafts and sent messages use `multipart/alternative` (plain text + styled HTML card), so they render correctly across email clients.

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
| `SERVER_API_KEY` | *(unset)* | If set, all non-health endpoints require `X-Api-Key: <value>` HTTP header |
| `APPROVAL_MODE` | `terminal` | `terminal` = operator prompt; `auto` = approve all (required on Cloud Run) |
| `GOOGLE_CREDENTIALS_PATH` | `credentials.json` | Path to OAuth 2.0 client credentials file (local dev) |
| `GOOGLE_TOKEN_PATH` | `token.json` | Path to cached OAuth token file (local dev) |
| `GOOGLE_CREDENTIALS_JSON` | *(unset)* | Raw JSON string of `credentials.json` — injected by Cloud Run from Secret Manager |
| `GOOGLE_TOKEN_JSON` | *(unset)* | Raw JSON string of `token.json` — injected by Cloud Run from Secret Manager |
| `GOOGLE_CREDENTIALS_B64` | *(unset)* | Base64-encoded `credentials.json` — alternative for plain Docker |
| `GOOGLE_TOKEN_B64` | *(unset)* | Base64-encoded `token.json` — alternative for plain Docker |
| `PORT` | `8000` | HTTP listen port (Cloud Run injects this automatically) |

> **`SERVER_API_KEY` vs `X-Api-Key`:** `SERVER_API_KEY` is the env var the server reads. `X-Api-Key` is the HTTP request header clients must send. Do not add `X-API-KEY` as an env var — it is not read by the application.

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

## Option D: GitHub + Google Cloud Run ✅ LIVE

**Status: Deployed and working**

| Detail | Value |
|---|---|
| Project | NextLeap (`gen-lang-client-0491576843`) |
| Service | `mcp-server-google` |
| Region | `europe-west1` |
| URL | `https://mcp-server-google-695514226672.europe-west1.run.app` |
| CD | Cloud Run built-in: push to `main` → Cloud Build → Cloud Run |
| Repository | `md-ammar-97/mcp-server-google` |

Deployment uses Cloud Run's built-in **"Continuously deploy from repository"** feature. Every push to `main` triggers Cloud Build, which builds the Docker image, pushes it to Artifact Registry (managed automatically — no manual repo needed), and deploys to Cloud Run. No GitHub Actions workflow, no `GCP_SA_KEY` / `GCP_PROJECT_ID` secrets in GitHub, no deployer service account required.

**How credentials flow at runtime:**
Cloud Run injects `GOOGLE_CREDENTIALS_JSON` and `GOOGLE_TOKEN_JSON` (from Secret Manager) as environment variables → `start.sh` writes them to `/tmp/credentials.json` and `/tmp/token.json` → sets `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_TOKEN_PATH` → `auth.py` reads from those paths.

---

### Step 1 — token.json (already done — skip)

`token.json` was pre-generated locally and stored in Secret Manager. Skip this step unless you get `invalid_grant` later.

---

### Step 2 — Enable required GCP APIs

```powershell
gcloud services enable `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  docs.googleapis.com `
  gmail.googleapis.com `
  --project gen-lang-client-0491576843
```

`docs.googleapis.com` and `gmail.googleapis.com` may already be enabled — running this again is safe. Cloud Build stores the built image in Artifact Registry automatically; no manual repository creation is needed.

---

### Step 3 — Store credentials in Secret Manager

Run from the project root where `credentials.json` and `token.json` exist.

```powershell
# credentials.json
gcloud secrets create google-mcp-credentials `
  --data-file="credentials.json" `
  --project gen-lang-client-0491576843

# token.json
gcloud secrets create google-mcp-token `
  --data-file="token.json" `
  --project gen-lang-client-0491576843

# API key — generate a strong random value
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$API_KEY = [Convert]::ToBase64String($bytes)
Write-Host "Your API key: $API_KEY"   # copy this — you will need it to call the API

Set-Content -NoNewline -Path .\server_api_key.txt -Value $API_KEY
gcloud secrets create google-mcp-api-key `
  --data-file="server_api_key.txt" `
  --project gen-lang-client-0491576843
Remove-Item .\server_api_key.txt
```

If any secret already exists, add a new version instead:

```powershell
gcloud secrets versions add google-mcp-credentials --data-file="credentials.json" --project gen-lang-client-0491576843
gcloud secrets versions add google-mcp-token       --data-file="token.json"       --project gen-lang-client-0491576843
```

---

### Step 4 — Grant runtime service account access to secrets

```powershell
$RUNTIME_SA = "695514226672-compute@developer.gserviceaccount.com"

foreach ($SECRET in @("google-mcp-credentials","google-mcp-token","google-mcp-api-key")) {
  gcloud secrets add-iam-policy-binding $SECRET `
    --member="serviceAccount:$RUNTIME_SA" `
    --role="roles/secretmanager.secretAccessor" `
    --project gen-lang-client-0491576843
}
```

---

### Step 5 — Create the Cloud Run service

Go to [Google Cloud Console → Cloud Run](https://console.cloud.google.com/run) → **Create Service**.

Choose **"Continuously deploy from a repository"** → **Set up with Cloud Build**.

| Setting | Value |
|---|---|
| Repository | `md-ammar-97/mcp-server-google` |
| Branch | `^main$` |
| Build type | **Dockerfile** |
| Dockerfile location | `/Dockerfile` |

Continue to service configuration:

| Setting | Value |
|---|---|
| Service name | `mcp-server-google` |
| Region | `europe-west1` |
| Authentication | **Allow unauthenticated invocations** |
| Minimum instances | `0` |
| Maximum instances | `2` |

Under **Container(s) → Variables & Secrets**:

Add environment variable:

| Name | Value |
|---|---|
| `APPROVAL_MODE` | `auto` |

Add secrets as environment variables:

| Environment variable | Secret | Version |
|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | `google-mcp-credentials` | `latest` |
| `GOOGLE_TOKEN_JSON` | `google-mcp-token` | `latest` |
| `SERVER_API_KEY` | `google-mcp-api-key` | `latest` |

> Do **not** set `PORT` — Cloud Run injects it automatically.
> Do **not** add `X-API-KEY` as an env var — it is not read by the application.

Click **Create**. Cloud Build triggers immediately.

---

### Step 6 — Monitor the build

**Cloud Run → your service → Revisions** or **Cloud Build → History**

A successful first build takes 2–4 minutes. The service URL appears in the Cloud Run console once the revision is healthy.

---

### Step 7 — Verify

```powershell
# Health check (no auth)
curl https://mcp-server-google-695514226672.europe-west1.run.app/health
# → {"status":"ok"}

# Gmail draft
curl -X POST https://mcp-server-google-695514226672.europe-west1.run.app/create_email_draft `
  -H "Content-Type: application/json" `
  -H "X-Api-Key: YOUR_API_KEY" `
  -d '{"to":"mohdammar97@gmail.com","subject":"Cloud Run Test","body":"# Test\n\n**Works from Cloud Run!**\n\n- Point one\n- Point two"}'
# → {"status":"ok","draft_id":"..."}

# Gmail send
curl -X POST https://mcp-server-google-695514226672.europe-west1.run.app/send_email `
  -H "Content-Type: application/json" `
  -H "X-Api-Key: YOUR_API_KEY" `
  -d '{"to":"recipient@example.com","subject":"Cloud Run Send Test","body":"# Test\n\n**This message was sent from Cloud Run.**"}'
# → {"status":"ok","message_id":"...","thread_id":"..."}

# Google Doc append
curl -X POST https://mcp-server-google-695514226672.europe-west1.run.app/append_to_doc `
  -H "Content-Type: application/json" `
  -H "X-Api-Key: YOUR_API_KEY" `
  -d '{"doc_id":"YOUR_DOC_ID","content":"# Cloud Run Test\n\nAppended from production."}'
# → {"status":"ok","doc_id":"...","chars_added":...}
```

---

### Logs

```powershell
gcloud run services logs read mcp-server-google `
  --region europe-west1 `
  --project gen-lang-client-0491576843 `
  --limit 100
```

---

### API Key rotation

Run these in a terminal where `gcloud` is authenticated:

```powershell
# 1. Generate a new key
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$NEW_KEY = [Convert]::ToBase64String($bytes)
Write-Host "New API key: $NEW_KEY"

# 2. Push a new secret version
Set-Content -NoNewline -Path .\server_api_key.txt -Value $NEW_KEY
gcloud secrets versions add google-mcp-api-key `
  --data-file="server_api_key.txt" `
  --project gen-lang-client-0491576843
Remove-Item .\server_api_key.txt

# 3. Redeploy Cloud Run to pick up the new version
gcloud run services update mcp-server-google `
  --region europe-west1 `
  --project gen-lang-client-0491576843 `
  --update-secrets SERVER_API_KEY=google-mcp-api-key:latest

# 4. Update local .env if needed
#    SERVER_API_KEY="<new key>"

# 5. Disable the old secret version (optional — list first)
gcloud secrets versions list google-mcp-api-key --project gen-lang-client-0491576843
# gcloud secrets versions disable VERSION_ID --secret google-mcp-api-key --project gen-lang-client-0491576843
```

---

### Token rotation (invalid_grant)

If you see `invalid_grant` in Cloud Run logs:

```powershell
# 1. Re-run OAuth on a machine with a browser
python -c "from auth import get_credentials; get_credentials()"

# 2. Push a new secret version
gcloud secrets versions add google-mcp-token `
  --data-file="token.json" `
  --project gen-lang-client-0491576843

# 3. Redeploy to pick up the new version
gcloud run services update mcp-server-google `
  --region europe-west1 `
  --project gen-lang-client-0491576843 `
  --update-secrets GOOGLE_TOKEN_JSON=google-mcp-token:latest
```

---

### Notes

| Topic | Detail |
|---|---|
| Credential injection | `start.sh` writes `GOOGLE_CREDENTIALS_JSON` / `GOOGLE_TOKEN_JSON` env vars to `/tmp` at container start, then sets `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_TOKEN_PATH` before uvicorn launches. |
| Token refresh | The refresh token inside `token.json` is long-lived. Google auto-issues a new access token on each start — no manual re-auth needed between deploys. |
| Artifact Registry | Cloud Build creates and manages the `cloud-run-source-deploy` repository automatically. |
| Scale to zero | Cloud Run scales to zero when idle. Cold start takes ~2 s. `APPROVAL_MODE=auto` prevents terminal prompts from blocking cold starts. |
| HTTPS | Cloud Run provides a managed TLS certificate on `*.run.app` automatically. No nginx needed. |
| Cost | Free tier: 2 M requests/month + 360,000 GB-s compute. Typical usage costs nothing. |
| No GitHub Actions | Cloud Run built-in CD handles the entire build/deploy pipeline. No `.github/workflows/` needed. |

---

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Build fails: `start.sh: not found` or `exec format error` | `start.sh` has CRLF line endings (Windows Git) | `.gitattributes` forces LF for `*.sh` — ensure it's committed |
| 500 / `EOFError` on Cloud Run | `APPROVAL_MODE=terminal` with no TTY | Set `APPROVAL_MODE=auto` via: `gcloud run services update mcp-server-google --region europe-west1 --project gen-lang-client-0491576843 --update-env-vars APPROVAL_MODE=auto` |
| Type conflict changing `SERVER_API_KEY` to a secret | Env var and secret reference conflict | Remove the plain env var first: `--remove-env-vars SERVER_API_KEY`, then add secret: `--update-secrets SERVER_API_KEY=google-mcp-api-key:latest` |
| `invalid_grant` | `token.json` expired or revoked | Re-run OAuth locally → `gcloud secrets versions add google-mcp-token` → redeploy |
| `401 Unauthorized` | API key missing or wrong | Send `X-Api-Key: <value>` header matching `SERVER_API_KEY` |
| `FileNotFoundError: credentials.json` | `GOOGLE_CREDENTIALS_PATH` wrong or secret not set | Verify `GOOGLE_CREDENTIALS_JSON` is set in Cloud Run from Secret Manager |
| `403 secretmanager.secretAccessor` | Runtime SA lacks IAM binding | Re-run Step 4 IAM grants |
| curl multiline failure: `-H: command not found` | Blank lines or trailing spaces after `\` in bash | Use `--data-binary @payload.json` with a `payload.json` file instead |

---

## Calling the API

All mutating endpoints require `X-Api-Key` if `SERVER_API_KEY` is set.

### Append to a Google Doc

```bash
curl -X POST http://localhost:8000/append_to_doc \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-secret-key" \
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
  -H "X-Api-Key: your-secret-key" \
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

Creating a draft only stores the message in Gmail Drafts. `APPROVAL_MODE=auto` approves the requested endpoint action; it does not convert a draft request into a send request.

### Send a Gmail message

Use the same payload shape as draft creation:

```bash
curl -X POST http://localhost:8000/send_email \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-secret-key" \
  -d '{
    "to": "recipient@example.com",
    "subject": "Project Update",
    "body": "# Project Update\n\n**Status:** On track\n\n- Milestone A complete\n- Milestone B in progress\n\n*Regards*"
  }'
```

Response:
```json
{"status": "ok", "message_id": "18f...", "thread_id": "18f..."}
```

---

## Credential Management

| File | Purpose | Secret? |
|---|---|---|
| `credentials.json` | OAuth 2.0 Client ID (app identity) | Yes — never commit |
| `token.json` | Cached user OAuth token (access + refresh) | Yes — never commit |

Both files are in `.gitignore`. In production:
- Both are stored in Google Secret Manager
- Cloud Run injects them as `GOOGLE_CREDENTIALS_JSON` / `GOOGLE_TOKEN_JSON`
- `start.sh` writes them to `/tmp` at container start

Token expiry:
- Access tokens expire every hour — the library refreshes them automatically using the refresh token
- Refresh tokens are long-lived but can be revoked from Google Account settings
- If revoked: re-run the OAuth browser flow locally → push new version to Secret Manager → redeploy

---

## Security Checklist

- [x] `SERVER_API_KEY` stored in Secret Manager — not in code or committed files
- [x] `credentials.json` and `token.json` stored in Secret Manager — not committed to git
- [x] `.env` in `.gitignore` — local secrets never committed
- [x] `APPROVAL_MODE=auto` set in Cloud Run (headless environment)
- [x] Cloud Run provides managed TLS — no manual HTTPS setup needed
- [x] Non-root Docker user (`appuser`) in Dockerfile
- [x] `.dockerignore` prevents secrets from entering Docker build context
- [x] No GitHub Actions — no `GCP_SA_KEY` or `GCP_PROJECT_ID` secrets in GitHub
- [x] Production verification covers document append, Gmail draft creation, and Gmail sending
- [ ] Rotate `SERVER_API_KEY` periodically (see API Key rotation section above)
- [ ] Token volume is writable so token refreshes persist (handled by `/tmp` in Cloud Run)
