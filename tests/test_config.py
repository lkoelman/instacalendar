from pathlib import Path

from instacalendar.config import AppConfig, AppPaths, ConfigStore


def test_config_round_trips_model_choices_and_export_defaults(tmp_path: Path) -> None:
    paths = AppPaths.from_base(tmp_path)
    store = ConfigStore(paths)
    config = AppConfig(
        instagram_username="musicfan",
        openrouter_text_model="openai/gpt-4o-mini",
        openrouter_vision_model="openai/gpt-4o",
        default_export="ics",
        google_calendar_id="primary",
    )

    store.save(config)

    assert store.load() == config
    assert paths.config_file.exists()


def test_config_load_returns_defaults_when_missing(tmp_path: Path) -> None:
    store = ConfigStore(AppPaths.from_base(tmp_path))

    assert store.load() == AppConfig()
