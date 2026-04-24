from __future__ import annotations

import os
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from instacalendar.cache import Cache
from instacalendar.config import AppConfig, AppPaths, ConfigStore
from instacalendar.exporters.google import GoogleCalendarExporter
from instacalendar.exporters.ics import IcsExporter
from instacalendar.extractors.openrouter import OpenRouterExtractor
from instacalendar.instagram import LiveInstagramClient
from instacalendar.models import EventDraft
from instacalendar.secrets import SecretStore


class Prompt(Protocol):
    def text(self, message: str, *, default: str | None = None, password: bool = False) -> str: ...

    def choose(self, message: str, choices: list[str], *, default: str | None = None) -> str: ...

    def confirm(self, message: str, *, default: bool = True) -> bool: ...


class Progress(Protocol):
    def status(self, message: str) -> AbstractContextManager[object]: ...


class NullProgress:
    def status(self, message: str) -> AbstractContextManager[object]:
        return nullcontext()


@dataclass(frozen=True)
class RunSummary:
    processed_posts: int
    approved_events: int
    exported_events: int
    destination: str


class AppRunner:
    def __init__(
        self, paths: AppPaths, prompt: Prompt, *, progress: Progress | None = None
    ) -> None:
        self.paths = paths
        self.prompt = prompt
        self.progress = progress or NullProgress()
        self.config_store = ConfigStore(paths)
        self.secret_store = SecretStore(paths.secret_fallback_file)
        self.cache = Cache(paths.cache_file)

    def configure(
        self,
        *,
        instagram_username: str | None = None,
        instagram_password: str | None = None,
        openrouter_api_key: str | None = None,
        openrouter_text_model: str | None = None,
        openrouter_vision_model: str | None = None,
        default_export: str | None = None,
        google_calendar_id: str | None = None,
    ) -> AppConfig:
        existing = self.config_store.load()
        config = AppConfig(
            instagram_username=instagram_username
            or existing.instagram_username
            or self.prompt.text("Instagram username"),
            openrouter_text_model=openrouter_text_model
            or existing.openrouter_text_model
            or self.prompt.text("OpenRouter text model", default="openai/gpt-4o-mini"),
            openrouter_vision_model=openrouter_vision_model
            or existing.openrouter_vision_model
            or self.prompt.text("OpenRouter vision model", default="openai/gpt-4o"),
            default_export=(default_export or existing.default_export),  # type: ignore[arg-type]
            google_calendar_id=google_calendar_id or existing.google_calendar_id,
        )
        self.config_store.save(config)
        self.secret_store.set(
            "instagram_password",
            instagram_password or self.prompt.text("Instagram password", password=True),
        )
        self.secret_store.set(
            "openrouter_api_key",
            self._resolve_openrouter_api_key(openrouter_api_key),
        )
        return config

    def run(
        self,
        *,
        collection: str | None = None,
        destination: str | None = None,
        ics_output: Path | None = None,
        google_service: object | None = None,
    ) -> RunSummary:
        with self.progress.status("Initializing cache ..."):
            self.cache.initialize()
        with self.progress.status("Loading configuration ..."):
            config = self.config_store.load()
        self._require_config(config)
        username = config.instagram_username or ""
        password = self.secret_store.get("instagram_password")
        api_key = self.secret_store.get("openrouter_api_key")
        if not password:
            password = self.prompt.text("Instagram password", password=True)
            self.secret_store.set("instagram_password", password)
        if not api_key:
            api_key = self._resolve_openrouter_api_key(None)
            self.secret_store.set("openrouter_api_key", api_key)

        instagram = LiveInstagramClient(username, password, self.paths.instagram_session_file)
        with self.progress.status("Authenticating with Instagram ..."):
            instagram.authenticate()
        if collection is None:
            with self.progress.status("Fetching collections ..."):
                collections = instagram.list_collections()
            collection = self.prompt.choose("Instagram saved collection", collections)
        with self.progress.status(f"Fetching posts from {collection} ..."):
            posts = instagram.fetch_collection_posts(collection)

        extractor = OpenRouterExtractor(
            api_key=api_key or "",
            text_model=config.openrouter_text_model or "",
            vision_model=config.openrouter_vision_model or "",
        )
        approved: list[tuple[str, EventDraft, str, int]] = []
        for post_number, post in enumerate(posts, start=1):
            with self.progress.status(
                f"Extracting event data from post {post_number}/{len(posts)} ..."
            ):
                result = extractor.extract(post)
            for index, draft in enumerate(result.events):
                uid = self.cache.stable_uid(
                    post.media_pk,
                    index,
                    draft.title,
                    draft.start.isoformat() if draft.start else "",
                )
                export_destination = destination or config.default_export
                destination_id = str(ics_output) if export_destination == "ics" else (
                    config.google_calendar_id or "primary"
                )
                if self.cache.has_export(uid, export_destination, destination_id):
                    continue
                if self._review(draft):
                    self.cache.record_review(post.media_pk, index, "approved", uid)
                    approved.append((uid, draft, post.media_pk, index))
                else:
                    self.cache.record_review(post.media_pk, index, "skipped", uid)

        export_destination = destination or config.default_export
        exported_count = 0
        if export_destination == "ics":
            output = ics_output or Path(self.prompt.text("ICS output path", default="events.ics"))
            with self.progress.status("Exporting approved events to ICS ..."):
                IcsExporter().export(output, [(uid, draft) for uid, draft, _, _ in approved])
            for uid, _draft, media_pk, index in approved:
                self.cache.record_export(
                    uid=uid,
                    media_pk=media_pk,
                    event_index=index,
                    destination_kind="ics",
                    destination_id=str(output),
                    remote_event_id=None,
                    exported_at=datetime.now(UTC),
                )
            exported_count = len(approved)
            destination_label = str(output)
        else:
            if google_service is None:
                with self.progress.status("Authenticating with Google Calendar ..."):
                    from instacalendar.google_auth import build_google_calendar_service

                    google_service = build_google_calendar_service(self.paths)
            calendar_id = config.google_calendar_id or "primary"
            exporter = GoogleCalendarExporter(google_service)
            for event_number, (uid, draft, media_pk, index) in enumerate(approved, start=1):
                with self.progress.status(
                    f"Exporting event {event_number}/{len(approved)} to Google Calendar ..."
                ):
                    remote_id = exporter.insert_if_missing(calendar_id, uid, draft)
                self.cache.record_export(
                    uid=uid,
                    media_pk=media_pk,
                    event_index=index,
                    destination_kind="google",
                    destination_id=calendar_id,
                    remote_event_id=remote_id,
                    exported_at=datetime.now(UTC),
                )
                exported_count += 1
            destination_label = f"google:{calendar_id}"

        return RunSummary(
            processed_posts=len(posts),
            approved_events=len(approved),
            exported_events=exported_count,
            destination=destination_label,
        )

    def _review(self, draft: EventDraft) -> bool:
        lines = [
            f"{draft.title}",
            f"Start: {draft.start}",
            f"Location: {draft.display_location() or 'not found'}",
            f"Confidence: {draft.confidence if draft.confidence is not None else 'unknown'}",
        ]
        return draft.is_exportable and self.prompt.confirm("\n".join(lines), default=True)

    def _resolve_openrouter_api_key(self, explicit_api_key: str | None) -> str:
        if explicit_api_key:
            return explicit_api_key
        environment_api_key = os.environ.get("OPENROUTER_API_KEY")
        if environment_api_key and self.prompt.confirm(
            "Use OPENROUTER_API_KEY from your environment?", default=True
        ):
            return environment_api_key
        return self.prompt.text("OpenRouter API key", password=True)

    def _require_config(self, config: AppConfig) -> None:
        missing = []
        if not config.instagram_username:
            missing.append("instagram_username")
        if not config.openrouter_text_model:
            missing.append("openrouter_text_model")
        if not config.openrouter_vision_model:
            missing.append("openrouter_vision_model")
        if missing:
            raise RuntimeError(f"Missing configuration: {', '.join(missing)}. Run auth first.")
