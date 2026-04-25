from datetime import date
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from instacalendar.cli import app
from instacalendar.runner import RunSummary


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


def test_cli_run_passes_post_filters_to_runner(monkeypatch) -> None:
    calls = []

    class FakeAppRunner:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def run(self, **kwargs) -> RunSummary:
            calls.append(kwargs)
            return RunSummary(
                processed_posts=1,
                approved_events=0,
                exported_events=0,
                destination="events.ics",
            )

    monkeypatch.setattr("instacalendar.cli.AppRunner", FakeAppRunner)

    result = CliRunner().invoke(
        app,
        ["run", "--posted-since", "2026-04-01", "--limit", "3"],
    )

    assert result.exit_code == 0
    assert calls[0]["posted_since"] == date(2026, 4, 1)
    assert calls[0]["limit"] == 3


def test_cli_default_command_passes_post_filters_to_runner(monkeypatch) -> None:
    calls = []

    class FakeAppRunner:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def configure(self):
            return SimpleNamespace(default_export="ics")

        def run(self, **kwargs) -> RunSummary:
            calls.append(kwargs)
            return RunSummary(
                processed_posts=1,
                approved_events=0,
                exported_events=0,
                destination="events.ics",
            )

    monkeypatch.setattr("instacalendar.cli.AppRunner", FakeAppRunner)

    result = CliRunner().invoke(app, ["--posted-since", "2026-04-01", "--limit", "3"])

    assert result.exit_code == 0
    assert calls[0]["posted_since"] == date(2026, 4, 1)
    assert calls[0]["limit"] == 3


def test_cli_rejects_non_positive_limit() -> None:
    result = CliRunner().invoke(app, ["run", "--limit", "0"])

    assert result.exit_code != 0


def test_cli_rejects_invalid_posted_since_date() -> None:
    result = CliRunner().invoke(app, ["run", "--posted-since", "04/01/2026"])

    assert result.exit_code != 0
