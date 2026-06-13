import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.compose",
]

_TOKEN = Path(os.environ.get("GOOGLE_TOKEN_PATH", "token.json"))
_CREDENTIALS = Path(os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json"))


def get_credentials() -> Credentials:
    creds: Credentials | None = None

    if _TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDENTIALS.exists():
                raise FileNotFoundError(
                    "credentials.json not found.\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials\n"
                    "(OAuth 2.0 Client ID → Desktop app) and place it in this directory."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=0)

        _TOKEN.write_text(creds.to_json())

    return creds
