from pathlib import Path

from typer.testing import CliRunner

from instacalendar.cli import app


def test_cli_cache_list_initializes_empty_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INSTACALENDAR_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["cache", "list"])

    assert result.exit_code == 0
    assert "No exports recorded" in result.stdout


def test_cli_auth_writes_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INSTACALENDAR_HOME", str(tmp_path))
    result = CliRunner().invoke(
        app,
        [
            "auth",
            "--instagram-username",
            "musicfan",
            "--instagram-password",
            "secret",
            "--openrouter-api-key",
            "key",
            "--openrouter-text-model",
            "text",
            "--openrouter-vision-model",
            "vision",
            "--default-export",
            "ics",
        ],
    )

    assert result.exit_code == 0
    assert "Saved configuration" in result.stdout
