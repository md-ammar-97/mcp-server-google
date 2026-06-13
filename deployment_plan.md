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
| `GOOGLE_CREDENTIALS_PATH` | `credentials.json` | Path to OAuth 2.0 client credentials file (local dev) |
| `GOOGLE_TOKEN_PATH` | `token.json` | Path to cached OAuth token file (local dev) |
| `GOOGLE_CREDENTIALS_JSON` | *(unset)* | Raw JSON string of `credentials.json` — injected by Cloud Run from Secret Manager |
| `GOOGLE_TOKEN_JSON` | *(unset)* | Raw JSON string of `token.json` — injected by Cloud Run from Secret Manager |
| `GOOGLE_CREDENTIALS_B64` | *(unset)* | Base64-encoded `credentials.json` — alternative for plain Docker |
| `GOOGLE_TOKEN_B64` | *(unset)* | Base64-encoded `token.json` — alternative for plain Docker |
| `PORT` | `8000` | HTTP listen port (Cloud Run and Railway inject this automatically) |

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

## Option D: GitHub + Google Cloud Run

**Project:** NextLeap (`gen-lang-client-0491576843`) · **Region:** `us-central1`

Deployment uses Cloud Run's built-in **"Continuously deploy from repository"** feature. Every push to `main` triggers Cloud Build, which builds the Docker image, pushes it to Artifact Registry (managed automatically — no manual repo needed), and deploys to Cloud Run. No GitHub Actions workflow or deployer service account is required.

**How credentials flow at runtime:**
Cloud Run injects `GOOGLE_CREDENTIALS_JSON` and `GOOGLE_TOKEN_JSON` (from Secret Manager) as environment variables → `start.sh` writes them to `/tmp/credentials.json` and `/tmp/token.json` → sets `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_TOKEN_PATH` → `auth.py` reads from those paths.

---

### Step 1 — token.json (already done — skip)

`token.json` was pre-generated locally. Skip this step unless you get `invalid_grant` later.

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
| Service name | `google-mcp-server` |
| Region | `us-central1` |
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

Click **Create**. Cloud Build triggers immediately.

---

### Step 6 — Monitor the build

**Cloud Run → your service → Revisions** or **Cloud Build → History**

A successful first build takes 2–4 minutes. The service URL appears in the Cloud Run console once the revision is healthy.

---

### Step 7 — Verify

```powershell
# Health check (no auth)
curl https://YOUR_SERVICE_URL/health
# → {"status":"ok"}

# Gmail draft
curl -X POST https://YOUR_SERVICE_URL/create_email_draft `
  -H "Content-Type: application/json" `
  -H "X-API-Key: YOUR_API_KEY" `
  -d '{"to":"mohdammar97@gmail.com","subject":"Cloud Run Test","body":"# Test\n\n**Works from Cloud Run!**\n\n- Point one\n- Point two"}'
# → {"status":"ok","draft_id":"..."}

# Google Doc append
curl -X POST https://YOUR_SERVICE_URL/append_to_doc `
  -H "Content-Type: application/json" `
  -H "X-API-Key: YOUR_API_KEY" `
  -d '{"doc_id":"YOUR_DOC_ID","content":"# Cloud Run Test\n\nAppended from production."}'
# → {"status":"ok","doc_id":"...","chars_added":...}
```

---

### Token rotation

If you get `invalid_grant`, regenerate `token.json` locally and push a new version:

```powershell
python -c "from auth import get_credentials; get_credentials()"

gcloud secrets versions add google-mcp-token `
  --data-file="token.json" `
  --project gen-lang-client-0491576843
```

Then push any commit to `main` (or redeploy from the console) to pick up the new version.

---

### Notes

| Topic | Detail |
|---|---|
| Credential injection | `start.sh` writes `GOOGLE_CREDENTIALS_JSON` / `GOOGLE_TOKEN_JSON` env vars to `/tmp` at container start, then sets `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_TOKEN_PATH` before uvicorn launches. |
| Token refresh | The refresh token inside `token.json` is long-lived. Google auto-issues a new access token on each start — no manual re-auth needed between deploys. |
| Artifact Registry | Cloud Build creates and manages the `cloud-run-source-deploy` repository automatically. |
| Scale to zero | Cloud Run scales to zero when idle. Cold start takes ~2 s. `APPROVAL_MODE=auto` prevents terminal prompts from blocking cold starts. |
| HTTPS | Cloud Run provides a managed TLS certificate on `*.run.app` automatically. |
| Cost | Free tier: 2 M requests/month + 360,000 GB-s compute. Typical usage costs nothing. |

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
