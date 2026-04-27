from __future__ import annotations

import json
import os
from copy import deepcopy
from importlib import resources
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from instacalendar.config import AppPaths

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

BUNDLED_GOOGLE_OAUTH_CLIENT_CONFIG: dict[str, Any] | None = None
_BUNDLED_CLIENT_RESOURCE = "google-oauth-client.json"


def build_google_calendar_service(paths: AppPaths):
    credentials = authorize_google_calendar(paths)
    return build("calendar", "v3", credentials=credentials)


def authorize_google_calendar(paths: AppPaths) -> Credentials:
    credentials = load_credentials(paths.google_token_file)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        client_config = load_client_config()
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        credentials = flow.run_local_server(port=0)
    paths.google_token_file.parent.mkdir(parents=True, exist_ok=True)
    paths.google_token_file.write_text(credentials.to_json())
    return credentials


def load_credentials(token_file: Path) -> Credentials | None:
    if not token_file.exists():
        return None
    credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if hasattr(credentials, "has_scopes") and not credentials.has_scopes(SCOPES):
        return None
    return credentials


def load_client_config() -> dict:
    if value := os.environ.get("GOOGLE_OAUTH_CLIENT_JSON"):
        return json.loads(value)
    if path := os.environ.get("GOOGLE_OAUTH_CLIENT_FILE"):
        return json.loads(Path(path).read_text())
    if BUNDLED_GOOGLE_OAUTH_CLIENT_CONFIG is not None:
        return deepcopy(BUNDLED_GOOGLE_OAUTH_CLIENT_CONFIG)
    if bundled_config := _load_bundled_client_config():
        return bundled_config
    raise RuntimeError(
        "Google OAuth client configuration is missing. "
        "Set GOOGLE_OAUTH_CLIENT_JSON or GOOGLE_OAUTH_CLIENT_FILE, or add the bundled "
        "Instacalendar OAuth client configuration."
    )


def _load_bundled_client_config() -> dict[str, Any] | None:
    try:
        client_file = resources.files("instacalendar").joinpath(_BUNDLED_CLIENT_RESOURCE)
        if not client_file.is_file():
            return None
        return json.loads(client_file.read_text())
    except FileNotFoundError:
        return None
