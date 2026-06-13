import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from docs_tool import append_to_doc
from gmail_tool import create_email_draft

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("google-mcp-server")

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

SERVER_API_KEY = os.environ.get("SERVER_API_KEY", "")
APPROVAL_MODE = os.environ.get("APPROVAL_MODE", "terminal").lower()
PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Google MCP Server", version="1.0.0")


@app.on_event("startup")
def _startup():
    log.info("Starting Google MCP Server on port %d", PORT)
    log.info("Approval mode: %s", APPROVAL_MODE)
    if SERVER_API_KEY:
        log.info("API key authentication: enabled")
    else:
        log.warning("SERVER_API_KEY not set — endpoint authentication is disabled")


# ---------------------------------------------------------------------------
# API key middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if request.url.path in ("/health", "/"):
        return await call_next(request)
    if SERVER_API_KEY and request.headers.get("X-API-Key") != SERVER_API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing X-API-Key header."})
    return await call_next(request)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "name": "Google MCP Server",
        "status": "running",
        "tools": [
            {"method": "POST", "path": "/append_to_doc",      "description": "Append text to a Google Doc"},
            {"method": "POST", "path": "/create_email_draft", "description": "Create a Gmail draft"},
        ],
        "docs": f"http://localhost:{PORT}/docs",
    }


@app.get("/health")
def health():
    """Lightweight liveness check — no auth, no Google API calls."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Approval helper
# ---------------------------------------------------------------------------

def _approve(action: str, payload: dict) -> bool:
    if APPROVAL_MODE == "auto":
        log.info("AUTO-APPROVED action=%s payload=%s", action, payload)
        return True

    print(f"\n{'='*50}")
    print(f"[ACTION] {action}")
    for key, value in payload.items():
        print(f"  {key}: {value}")
    print("=" * 50)
    answer = input("Approve? (y/n): ").strip().lower()
    approved = answer == "y"
    log.info("Operator %s action=%s", "approved" if approved else "rejected", action)
    return approved


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AppendDocRequest(BaseModel):
    doc_id: str
    content: str


class CreateDraftRequest(BaseModel):
    to: str
    subject: str
    body: str


# ---------------------------------------------------------------------------
# Endpoints  (sync so input() blocks without touching the event loop)
# ---------------------------------------------------------------------------

@app.post("/append_to_doc")
def append_doc_endpoint(req: AppendDocRequest):
    log.info("Received append_to_doc request doc_id=%s chars=%d", req.doc_id, len(req.content))
    try:
        payload = {"doc_id": req.doc_id, "content": req.content}
        if not _approve("append_to_doc", payload):
            raise HTTPException(status_code=403, detail="Action rejected by operator.")
        result = append_to_doc(req.doc_id, req.content)
        log.info("append_to_doc completed doc_id=%s chars_added=%s", req.doc_id, result.get("chars_added"))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/create_email_draft")
def create_draft_endpoint(req: CreateDraftRequest):
    log.info("Received create_email_draft request to=%s subject=%s", req.to, req.subject)
    try:
        preview = req.body[:100] + ("..." if len(req.body) > 100 else "")
        payload = {"to": req.to, "subject": req.subject, "body (preview)": preview}
        if not _approve("create_email_draft", payload):
            raise HTTPException(status_code=403, detail="Action rejected by operator.")
        result = create_email_draft(req.to, req.subject, req.body)
        log.info("create_email_draft completed draft_id=%s", result.get("draft_id"))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)
