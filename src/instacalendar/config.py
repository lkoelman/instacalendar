from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel

APP_NAME = "instacalendar"


class AppPaths(BaseModel):
    config_dir: Path
    data_dir: Path

    @classmethod
    def default(cls) -> AppPaths:
        override = os.environ.get("INSTACALENDAR_HOME")
        if override:
            return cls.from_base(Path(override))
        return cls(
            config_dir=Path(user_config_dir(APP_NAME, appauthor=False)),
            data_dir=Path(user_data_dir(APP_NAME, appauthor=False)),
        )

    @classmethod
    def from_base(cls, base: Path) -> AppPaths:
        return cls(config_dir=base / "config", data_dir=base / "data")

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def cache_file(self) -> Path:
        return self.data_dir / "cache.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def instagram_session_file(self) -> Path:
        return self.data_dir / "instagram-session.json"

    @property
    def google_token_file(self) -> Path:
        return self.data_dir / "google-token.json"


class AppConfig(BaseModel):
    instagram_username: str | None = None
    openrouter_text_model: str | None = None
    openrouter_vision_model: str | None = None
    openrouter_video_model: str | None = None
    default_export: Literal["ics", "google"] = "ics"
    google_calendar_id: str | None = None


class ConfigStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def load(self) -> AppConfig:
        if not self.paths.config_file.exists():
            return AppConfig()
        return AppConfig.model_validate_json(self.paths.config_file.read_text())

    def save(self, config: AppConfig) -> None:
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_file.write_text(json.dumps(config.model_dump(), indent=2) + "\n")
