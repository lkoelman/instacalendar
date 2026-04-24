from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from instacalendar.config import AppPaths

SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar"]


def build_google_calendar_service(paths: AppPaths):
    credentials = _load_credentials(paths.google_token_file)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        client_config = _load_client_config()
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        credentials = flow.run_local_server(port=0)
    paths.google_token_file.parent.mkdir(parents=True, exist_ok=True)
    paths.google_token_file.write_text(credentials.to_json())
    return build("calendar", "v3", credentials=credentials)


def _load_credentials(token_file: Path) -> Credentials | None:
    if not token_file.exists():
        return None
    return Credentials.from_authorized_user_file(str(token_file), SCOPES)


def _load_client_config() -> dict:
    if value := os.environ.get("GOOGLE_OAUTH_CLIENT_JSON"):
        return json.loads(value)
    if path := os.environ.get("GOOGLE_OAUTH_CLIENT_FILE"):
        return json.loads(Path(path).read_text())
    raise RuntimeError(
        "Google export requires GOOGLE_OAUTH_CLIENT_JSON or GOOGLE_OAUTH_CLIENT_FILE."
    )
