import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from instacalendar import google_auth
from instacalendar.config import AppPaths


def test_google_auth_uses_calendar_events_scope_only() -> None:
    assert google_auth.SCOPES == ["https://www.googleapis.com/auth/calendar.events"]


def test_load_client_config_prefers_json_environment(monkeypatch) -> None:
    monkeypatch.setattr(google_auth, "BUNDLED_GOOGLE_OAUTH_CLIENT_CONFIG", {"installed": {}})
    monkeypatch.setenv(
        "GOOGLE_OAUTH_CLIENT_JSON",
        json.dumps({"installed": {"client_id": "from-json"}}),
    )

    assert google_auth.load_client_config()["installed"]["client_id"] == "from-json"


def test_load_client_config_prefers_file_over_bundled(tmp_path: Path, monkeypatch) -> None:
    client_file = tmp_path / "client.json"
    client_file.write_text(json.dumps({"installed": {"client_id": "from-file"}}))
    monkeypatch.setattr(google_auth, "BUNDLED_GOOGLE_OAUTH_CLIENT_CONFIG", {"installed": {}})
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_FILE", str(client_file))

    assert google_auth.load_client_config()["installed"]["client_id"] == "from-file"


def test_load_client_config_falls_back_to_bundled(monkeypatch) -> None:
    monkeypatch.setattr(
        google_auth,
        "BUNDLED_GOOGLE_OAUTH_CLIENT_CONFIG",
        {"installed": {"client_id": "bundled"}},
    )

    assert google_auth.load_client_config()["installed"]["client_id"] == "bundled"


def test_load_client_config_errors_when_no_client_available(monkeypatch) -> None:
    monkeypatch.setattr(google_auth, "BUNDLED_GOOGLE_OAUTH_CLIENT_CONFIG", None)
    monkeypatch.setattr(google_auth, "_load_bundled_client_config", Mock(return_value=None))

    with pytest.raises(RuntimeError, match="Google OAuth client configuration is missing"):
        google_auth.load_client_config()


def test_load_credentials_ignores_token_without_required_scopes(
    tmp_path: Path, monkeypatch
) -> None:
    token_file = tmp_path / "google-token.json"
    token_file.write_text("{}")
    credentials = SimpleNamespace(has_scopes=Mock(return_value=False))
    from_file = Mock(return_value=credentials)
    monkeypatch.setattr(google_auth.Credentials, "from_authorized_user_file", from_file)

    assert google_auth.load_credentials(token_file) is None
    from_file.assert_called_once_with(str(token_file), google_auth.SCOPES)
    credentials.has_scopes.assert_called_once_with(google_auth.SCOPES)


def test_authorize_google_calendar_saves_new_credentials(tmp_path: Path, monkeypatch) -> None:
    paths = AppPaths.from_base(tmp_path)
    credentials = SimpleNamespace(
        valid=True, expired=False, refresh_token=None, to_json=lambda: "{}"
    )
    flow = SimpleNamespace(run_local_server=Mock(return_value=credentials))
    flow_factory = Mock(return_value=flow)
    monkeypatch.setattr(google_auth, "load_credentials", Mock(return_value=None))
    monkeypatch.setattr(google_auth, "load_client_config", Mock(return_value={"installed": {}}))
    monkeypatch.setattr(google_auth.InstalledAppFlow, "from_client_config", flow_factory)

    result = google_auth.authorize_google_calendar(paths)

    assert result is credentials
    assert paths.google_token_file.read_text() == "{}"
    flow_factory.assert_called_once_with({"installed": {}}, google_auth.SCOPES)
    flow.run_local_server.assert_called_once()
