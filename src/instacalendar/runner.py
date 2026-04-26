from __future__ import annotations

import os
import re
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime
from mimetypes import guess_extension, guess_type
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from instacalendar.cache import Cache, CachedMedia
from instacalendar.config import AppConfig, AppPaths, ConfigStore
from instacalendar.exporters.google import GoogleCalendarExporter
from instacalendar.exporters.ics import IcsExporter
from instacalendar.extractors.openrouter import OpenRouterExtractor
from instacalendar.instagram import LiveInstagramClient
from instacalendar.models import (
    EventDraft,
    ExtractionResult,
    ImageReference,
    InstagramPost,
    VideoReference,
)
from instacalendar.secrets import SecretStore


class Prompt(Protocol):
    def text(self, message: str, *, default: str | None = None, password: bool = False) -> str: ...

    def choose(self, message: str, choices: list[str], *, default: str | None = None) -> str: ...

    def confirm(self, message: str, *, default: bool = True) -> bool: ...


class Progress(Protocol):
    def status(self, message: str) -> AbstractContextManager[object]: ...

    def task(self, description: str, *, total: int) -> ProgressTask: ...


class ProgressTask(Protocol):
    def __enter__(self) -> ProgressTask: ...

    def __exit__(self, exc_type, exc_value, traceback) -> None: ...

    def update(self, message: str) -> None: ...

    def advance(self) -> None: ...

    def report(self, message: str) -> None: ...


class NullProgress:
    def status(self, message: str) -> AbstractContextManager[object]:
        return nullcontext()

    def task(self, description: str, *, total: int) -> ProgressTask:
        return NullProgressTask()


class NullProgressTask:
    def __enter__(self) -> NullProgressTask:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def update(self, message: str) -> None:
        return None

    def advance(self) -> None:
        return None

    def report(self, message: str) -> None:
        return None


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
        openrouter_video_model: str | None = None,
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
            openrouter_video_model=openrouter_video_model or existing.openrouter_video_model,
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
        posted_since: date | None = None,
        limit: int | None = None,
        from_cache: bool = False,
    ) -> RunSummary:
        with self.progress.status("Initializing cache ..."):
            self.cache.initialize()
        with self.progress.status("Loading configuration ..."):
            config = self.config_store.load()
        self._require_config(config, require_instagram=not from_cache)
        username = config.instagram_username or ""
        api_key = self.secret_store.get("openrouter_api_key")
        if not api_key:
            api_key = self._resolve_openrouter_api_key(None)
            self.secret_store.set("openrouter_api_key", api_key)

        if from_cache:
            if collection is None:
                collections = self.cache.list_cached_collections()
                if not collections:
                    raise RuntimeError("No cached posts found. Run without --from-cache first.")
                collection = self.prompt.choose("Cached Instagram collection", collections)
            posts = self.cache.load_cached_posts(collection)
            if not posts:
                raise RuntimeError(f"No cached posts found for collection {collection!r}.")
        else:
            password = self.secret_store.get("instagram_password")
            if not password:
                password = self.prompt.text("Instagram password", password=True)
                self.secret_store.set("instagram_password", password)
            instagram = LiveInstagramClient(username, password, self.paths.instagram_session_file)
            with self.progress.status("Authenticating with Instagram ..."):
                instagram.authenticate()
            if collection is None:
                with self.progress.status("Fetching collections ..."):
                    collections = instagram.list_collections()
                collection = self.prompt.choose("Instagram saved collection", collections)
            with self.progress.status(f"Fetching posts from {collection} ..."):
                posts = instagram.fetch_collection_posts(collection)
        if posted_since is not None:
            posts = [
                post
                for post in posts
                if post.taken_at is not None and post.taken_at.date() >= posted_since
            ]
        if limit is not None:
            posts = posts[:limit]
        if not from_cache:
            with self.progress.status(f"Caching posts from {collection} ..."):
                posts = self._cache_posts(collection or "", posts)

        extractor = OpenRouterExtractor(
            api_key=api_key or "",
            text_model=config.openrouter_text_model or "",
            vision_model=config.openrouter_vision_model or "",
            video_model=config.openrouter_video_model or config.openrouter_vision_model or "",
        )
        approved: list[tuple[str, EventDraft, str, int]] = []
        with self.progress.task("Processing posts", total=len(posts)) as progress_task:
            for post_number, post in enumerate(posts, start=1):
                extraction_statuses: list[str] = []

                def report_extraction_status(
                    message: str,
                    *,
                    post_number: int = post_number,
                    statuses: list[str] = extraction_statuses,
                ) -> None:
                    statuses.append(message)
                    progress_task.update(f"Post {post_number}/{len(posts)}: {message}")

                result = extractor.extract(post, status_callback=report_extraction_status)
                progress_task.report(
                    self._post_extraction_summary(post, result, extraction_statuses)
                )
                progress_task.advance()
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

    def _post_extraction_summary(
        self, post: InstagramPost, result: ExtractionResult, extraction_statuses: list[str]
    ) -> str:
        poster = post.poster_username or "unknown"
        posted_date = post.taken_at.date().isoformat() if post.taken_at else "unknown date"
        if not result.events:
            return f"@{poster} ({posted_date}) - failed - no event details"
        source = self._extraction_source(extraction_statuses)
        details = "; ".join(self._event_summary(draft) for draft in result.events)
        return f"@{poster} ({posted_date}) - got event from {source} - {details}"

    def _extraction_source(self, extraction_statuses: list[str]) -> str:
        if "Interpreting video" in extraction_statuses:
            return "video"
        if "Interpreting image" in extraction_statuses:
            return "image"
        return "text"

    def _event_summary(self, draft: EventDraft) -> str:
        event_date = draft.start.date().isoformat() if draft.start else "date unknown"
        location = draft.display_location() or "location unknown"
        return f"{event_date} at {location}"

    def _resolve_openrouter_api_key(self, explicit_api_key: str | None) -> str:
        if explicit_api_key:
            return explicit_api_key
        environment_api_key = os.environ.get("OPENROUTER_API_KEY")
        if environment_api_key and self.prompt.confirm(
            "Use OPENROUTER_API_KEY from your environment?", default=True
        ):
            return environment_api_key
        return self.prompt.text("OpenRouter API key", password=True)

    def _cache_posts(self, collection_name: str, posts: list[InstagramPost]) -> list[InstagramPost]:
        cached_posts = []
        fetched_at = datetime.now(UTC)
        for post in posts:
            media_records = self._download_post_media(collection_name, post)
            cached_post = self._post_with_cached_media(post, media_records)
            self.cache.upsert_cached_post(
                collection_name=collection_name,
                post=post,
                fetched_at=fetched_at,
                media=media_records,
            )
            cached_posts.append(cached_post)
        return cached_posts

    def _download_post_media(
        self, collection_name: str, post: InstagramPost
    ) -> list[CachedMedia]:
        records: list[CachedMedia] = []
        for kind, references in (("image", post.images), ("video", post.videos)):
            for index, reference in enumerate(references):
                source_url = reference.uri
                try:
                    local_path = self._download_media_file(
                        collection_name=collection_name,
                        media_pk=post.media_pk,
                        media_kind=kind,
                        media_index=index,
                        source_url=source_url,
                    )
                except Exception as error:
                    records.append(
                        CachedMedia(
                            collection_name=collection_name,
                            media_pk=post.media_pk,
                            media_kind=kind,
                            media_index=index,
                            source_url=source_url,
                            local_path=None,
                            status="failed",
                            error=str(error),
                        )
                    )
                else:
                    records.append(
                        CachedMedia(
                            collection_name=collection_name,
                            media_pk=post.media_pk,
                            media_kind=kind,
                            media_index=index,
                            source_url=source_url,
                            local_path=str(local_path),
                            status="cached",
                            error=None,
                        )
                    )
        return records

    def _download_media_file(
        self,
        *,
        collection_name: str,
        media_pk: str,
        media_kind: str,
        media_index: int,
        source_url: str,
    ) -> Path:
        directory = self.paths.media_dir / self._slug(collection_name) / media_pk
        directory.mkdir(parents=True, exist_ok=True)
        extension = self._media_extension(source_url, media_kind)
        path = directory / f"{media_kind}-{media_index}{extension}"
        if path.exists():
            return path
        response = httpx.get(source_url, timeout=60, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)
        return path

    def _media_extension(self, source_url: str, media_kind: str) -> str:
        parsed_path = Path(urlparse(source_url).path)
        if parsed_path.suffix:
            return parsed_path.suffix.split("?")[0]
        if content_type := guess_type(source_url)[0]:
            return guess_extension(content_type) or self._default_media_extension(media_kind)
        return self._default_media_extension(media_kind)

    def _default_media_extension(self, media_kind: str) -> str:
        return ".mp4" if media_kind == "video" else ".jpg"

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
        return slug or "collection"

    def _post_with_cached_media(
        self, post: InstagramPost, media_records: list[CachedMedia]
    ) -> InstagramPost:
        images = [
            ImageReference(uri=record.local_path or record.source_url)
            for record in media_records
            if record.media_kind == "image"
        ]
        videos = [
            VideoReference(uri=record.local_path or record.source_url)
            for record in media_records
            if record.media_kind == "video"
        ]
        return post.model_copy(update={"images": images, "videos": videos})

    def _require_config(self, config: AppConfig, *, require_instagram: bool = True) -> None:
        missing = []
        if require_instagram and not config.instagram_username:
            missing.append("instagram_username")
        if not config.openrouter_text_model:
            missing.append("openrouter_text_model")
        if not config.openrouter_vision_model:
            missing.append("openrouter_vision_model")
        if missing:
            raise RuntimeError(f"Missing configuration: {', '.join(missing)}. Run auth first.")
