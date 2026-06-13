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

Every push to `main` triggers a GitHub Actions workflow that builds the Docker image, pushes it to Artifact Registry, and deploys it to Cloud Run. Credentials are stored in Google Secret Manager and injected at runtime — never committed or baked into the image.

### Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and initialised (`gcloud init`)
- This repo pushed to GitHub

---

### Step 1 — Pre-generate token.json locally (one-time)

The OAuth browser flow must run on a machine with a browser:

```bash
pip install -r requirements.txt
python -c "from auth import get_credentials; get_credentials()"
# → Browser opens → approve → token.json is written
```

---

### Step 2 — Enable required GCP APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  --project YOUR_PROJECT_ID
```

---

### Step 3 — Create an Artifact Registry repository

```bash
gcloud artifacts repositories create google-mcp-server \
  --repository-format=docker \
  --location=us-central1 \
  --project YOUR_PROJECT_ID
```

---

### Step 4 — Store credentials in Secret Manager

```bash
# credentials.json → secret
gcloud secrets create google-mcp-credentials \
  --data-file=credentials.json \
  --project YOUR_PROJECT_ID

# token.json → secret
gcloud secrets create google-mcp-token \
  --data-file=token.json \
  --project YOUR_PROJECT_ID

# API key → secret  (generate a strong random value)
echo -n "YOUR_STRONG_API_KEY" | \
  gcloud secrets create google-mcp-api-key --data-file=- \
  --project YOUR_PROJECT_ID
```

Grant the Cloud Run runtime service account access to read them:

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for SECRET in google-mcp-credentials google-mcp-token google-mcp-api-key; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:$RUNTIME_SA" \
    --role="roles/secretmanager.secretAccessor" \
    --project YOUR_PROJECT_ID
done
```

---

### Step 5 — Create a GitHub Actions deployer service account

```bash
gcloud iam service-accounts create github-actions-deployer \
  --display-name="GitHub Actions Deployer" \
  --project YOUR_PROJECT_ID

DEPLOYER_SA="github-actions-deployer@YOUR_PROJECT_ID.iam.gserviceaccount.com"

# Roles needed to build, push, and deploy
for ROLE in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$DEPLOYER_SA" \
    --role="$ROLE"
done

# Download the key — you will add this to GitHub secrets
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account="$DEPLOYER_SA"
```

> `github-actions-key.json` is a secret — do not commit it. Add it to GitHub and delete the local file.

---

### Step 6 — Add GitHub repository secrets

In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name | Value |
|---|---|
| `GCP_PROJECT_ID` | Your Google Cloud project ID (e.g. `my-project-123`) |
| `GCP_SA_KEY` | Full contents of `github-actions-key.json` |

Then delete the local key file:

```bash
del github-actions-key.json   # Windows
# rm github-actions-key.json  # macOS / Linux
```

---

### Step 7 — Push to trigger the first deploy

The workflow in `.github/workflows/deploy.yml` runs automatically on every push to `main`:

```bash
git push origin main
```

Monitor progress: **GitHub repo → Actions tab**

On success the workflow prints the Cloud Run service URL.

---

### Step 8 — Verify

```bash
curl https://YOUR_SERVICE_URL/health
# → {"status":"ok"}
```

The Cloud Run URL follows the pattern `https://google-mcp-server-XXXXXXXX-uc.a.run.app`.

---

### Token rotation

When `token.json` needs to be refreshed:

```bash
# 1. Re-run OAuth locally to get a new token.json
python -c "from auth import get_credentials; get_credentials()"

# 2. Add a new version to the secret
gcloud secrets versions add google-mcp-token \
  --data-file=token.json \
  --project YOUR_PROJECT_ID

# 3. Re-deploy (or push any commit to main) to pick up the new version
```

---

### Notes

| Topic | Detail |
|---|---|
| Credential injection | Cloud Run links `google-mcp-credentials` and `google-mcp-token` secrets as env vars (`GOOGLE_CREDENTIALS_JSON` / `GOOGLE_TOKEN_JSON`). `start.sh` writes them to `/tmp` and sets the path env vars before starting uvicorn. |
| Token refresh | The embedded refresh token means Google auto-issues a new access token on each request — no manual re-auth between deployments. |
| Scaling to zero | Cloud Run scales to zero when idle. `APPROVAL_MODE=auto` is set by the workflow so no terminal prompts block cold starts. |
| HTTPS | Cloud Run provides a managed TLS certificate on the `*.run.app` domain automatically. Custom domains can be mapped in the Cloud Run console. |
| Cost | The free tier includes 2 million requests/month and 360,000 GB-seconds of compute. Typical usage costs nothing. |

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
