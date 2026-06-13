import base64
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from auth import get_credentials
from googleapiclient.discovery import build

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_HTML_TEMPLATE = (
    '<!DOCTYPE html><html>'
    '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
    '<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,Helvetica,sans-serif;">'
    '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;">'
    '<tr><td align="center" style="padding:32px 16px;">'
    '<table width="100%" cellpadding="0" cellspacing="0"'
    ' style="max-width:600px;background:#ffffff;border-radius:6px;border:1px solid #e0e0e0;">'
    '<tr><td style="padding:40px 48px;color:#222222;font-size:15px;line-height:1.75;">'
    "BODY_PLACEHOLDER"
    '</td></tr></table></td></tr></table>'
    '</body></html>'
)


def _inline_html(text: str) -> str:
    """Convert inline markdown to safe HTML."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*',     r'<strong>\1</strong>',          text)
    text = re.sub(r'\*(.+?)\*',         r'<em>\1</em>',                  text)
    text = re.sub(r'_(.+?)_',           r'<em>\1</em>',                  text)
    return text


def _md_to_html(text: str) -> str:
    """Convert markdown body text to an HTML fragment."""
    parts = []
    in_ul = False
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = line.strip()
        if s.startswith("# "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append(
                f'<h1 style="margin:0 0 16px;font-size:24px;font-weight:700;'
                f'color:#111111;line-height:1.3;">{_inline_html(s[2:])}</h1>'
            )
        elif s.startswith("## "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append(
                f'<h2 style="margin:24px 0 10px;font-size:20px;font-weight:700;'
                f'color:#111111;line-height:1.3;">{_inline_html(s[3:])}</h2>'
            )
        elif s.startswith("### "):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append(
                f'<h3 style="margin:20px 0 8px;font-size:17px;font-weight:700;'
                f'color:#111111;line-height:1.3;">{_inline_html(s[4:])}</h3>'
            )
        elif s.startswith("- ") or s.startswith("* "):
            if not in_ul:
                parts.append('<ul style="margin:8px 0 12px;padding-left:24px;">')
                in_ul = True
            parts.append(f'<li style="margin:4px 0;">{_inline_html(s[2:])}</li>')
        elif s in ("---", "***", "___"):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append('<hr style="border:none;border-top:1px solid #e8e8e8;margin:24px 0;">')
        elif s == "":
            if in_ul:
                parts.append("</ul>")
                in_ul = False
        else:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append(f'<p style="margin:0 0 14px;color:#222222;">{_inline_html(s)}</p>')

    if in_ul:
        parts.append("</ul>")
    return "\n".join(parts)


def create_email_draft(to: str, subject: str, body: str) -> dict:
    """Create a Gmail draft with plain-text and styled HTML parts from markdown body."""
    if not _EMAIL_RE.match(to):
        raise ValueError(f"Invalid email address: {to!r}")

    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    html_body = _HTML_TEMPLATE.replace("BODY_PLACEHOLDER", _md_to_html(body))

    message = MIMEMultipart("alternative")
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()

    return {"status": "ok", "draft_id": draft["id"]}
