from datetime import date
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from instacalendar.cli import app
from instacalendar.runner import ModelUsageTotal, RunSummary


def test_cli_cache_list_initializes_empty_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INSTACALENDAR_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["cache", "list-events"])

    assert result.exit_code == 0
    assert "No exports recorded" in result.stdout


def test_cli_cache_list_command_is_removed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INSTACALENDAR_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["cache", "list"])

    assert result.exit_code != 0


def test_cli_cache_list_posts_shows_cached_posts(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from instacalendar.cache import Cache
    from instacalendar.config import AppPaths
    from instacalendar.models import InstagramPost

    monkeypatch.setenv("INSTACALENDAR_HOME", str(tmp_path))
    cache = Cache(AppPaths.from_base(tmp_path).cache_file)
    cache.initialize()
    cache.upsert_cached_post(
        collection_name="Concerts",
        post=InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="May 3 at The Room with a long lineup",
            taken_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
            media_kind="1",
        ),
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("UTC")),
        media=[],
    )

    result = CliRunner().invoke(app, ["cache", "list-posts"])

    assert result.exit_code == 0
    assert "Collection" in result.stdout
    assert "Concerts" in result.stdout
    assert "abc" in result.stdout


def test_cli_cache_info_shows_location_totals_and_collection_breakdown(
    tmp_path: Path, monkeypatch
) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from instacalendar.cache import Cache, CachedMedia
    from instacalendar.config import AppPaths
    from instacalendar.models import InstagramPost

    monkeypatch.setenv("INSTACALENDAR_HOME", str(tmp_path))
    paths = AppPaths.from_base(tmp_path)
    media_file = paths.media_dir / "Concerts" / "1" / "image-0.jpg"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"image bytes")
    cache = Cache(paths.cache_file)
    cache.initialize()
    cache.upsert_cached_post(
        collection_name="Concerts",
        post=InstagramPost(media_pk="1", caption="", media_kind="1"),
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("UTC")),
        media=[
            CachedMedia(
                collection_name="Concerts",
                media_pk="1",
                media_kind="image",
                media_index=0,
                source_url="https://cdn.example/post.jpg",
                local_path=str(media_file),
                status="cached",
                error=None,
            )
        ],
    )

    result = CliRunner().invoke(app, ["cache", "info"])

    assert result.exit_code == 0
    assert str(paths.cache_file) in result.stdout
    assert str(paths.media_dir) in result.stdout
    assert "Total storage" in result.stdout
    assert "Concerts" in result.stdout
    assert "Images" in result.stdout


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


def test_cli_auth_accepts_openrouter_video_model(tmp_path: Path, monkeypatch) -> None:
    from instacalendar.config import AppPaths, ConfigStore

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
            "--openrouter-video-model",
            "video",
            "--default-export",
            "ics",
        ],
    )

    assert result.exit_code == 0
    assert ConfigStore(AppPaths.from_base(tmp_path)).load().openrouter_video_model == "video"


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


def test_cli_run_prints_extraction_cost_summary(monkeypatch) -> None:
    class FakeAppRunner:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def run(self, **kwargs) -> RunSummary:
            return RunSummary(
                processed_posts=2,
                approved_events=0,
                exported_events=0,
                destination="events.ics",
                extraction_usage_by_model={
                    "text": ModelUsageTotal(
                        prompt_tokens=200,
                        completion_tokens=50,
                        total_tokens=250,
                        estimated_cost_usd=0.002,
                        calls=2,
                    )
                },
            )

    monkeypatch.setattr("instacalendar.cli.AppRunner", FakeAppRunner)

    result = CliRunner().invoke(app, ["run"])

    assert result.exit_code == 0
    assert "Extraction cost: est. $0.0020" in result.stdout
    assert "text: 250 tokens ($0.0020, 2 calls)" in result.stdout


def test_cli_run_passes_from_cache_to_runner(monkeypatch) -> None:
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

    result = CliRunner().invoke(app, ["run", "--from-cache", "--collection", "Concerts"])

    assert result.exit_code == 0
    assert calls[0]["from_cache"] is True
    assert calls[0]["collection"] == "Concerts"


def test_cli_run_passes_event_cache_options_to_runner(monkeypatch) -> None:
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
        ["run", "--ignore-event-cache", "--event-cache-key", "post,media"],
    )

    assert result.exit_code == 0
    assert calls[0]["ignore_event_cache"] is True
    assert calls[0]["event_cache_key"] == "post,media"


def test_cli_run_rejects_invalid_event_cache_key() -> None:
    result = CliRunner().invoke(app, ["run", "--event-cache-key", "media"])

    assert result.exit_code != 0


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
