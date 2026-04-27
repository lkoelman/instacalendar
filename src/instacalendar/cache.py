from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from instacalendar.models import (
    ExtractionResult,
    ImageReference,
    InstagramPost,
    VideoReference,
)

EVENT_CACHE_KEYS = {"post", "post,media", "model", "model,media"}


@dataclass(frozen=True)
class CachedExport:
    uid: str
    media_pk: str
    event_index: int
    destination_kind: str
    destination_id: str
    remote_event_id: str | None
    exported_at: str


@dataclass(frozen=True)
class CachedMedia:
    collection_name: str
    media_pk: str
    media_kind: str
    media_index: int
    source_url: str
    local_path: str | None
    status: str
    error: str | None


@dataclass(frozen=True)
class CachedPostSummary:
    collection_name: str
    media_pk: str
    shortcode: str | None
    taken_at: str | None
    media_kind: str
    fetched_at: str
    cached_images: int
    cached_videos: int
    missing_media: int
    caption_preview: str


@dataclass(frozen=True)
class CacheCollectionInfo:
    collection_name: str
    file_counts: dict[str, int]
    size_bytes: int
    missing_media_count: int


@dataclass(frozen=True)
class CacheInfo:
    cache_file: Path
    media_dir: Path
    database_size_bytes: int
    media_size_bytes: int
    total_size_bytes: int
    total_file_counts: dict[str, int]
    missing_media_count: int
    collections: list[CacheCollectionInfo]


@dataclass(frozen=True)
class CachedExtraction:
    media_pk: str
    model_signature: str
    source_media_kind: str
    extracted_at: str
    status: str
    event_count: int
    event_titles: list[str]
    warnings_count: int


class Cache:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    media_pk TEXT NOT NULL,
                    event_index INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (media_pk, event_index)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exports (
                    uid TEXT NOT NULL,
                    media_pk TEXT NOT NULL,
                    event_index INTEGER NOT NULL,
                    destination_kind TEXT NOT NULL,
                    destination_id TEXT NOT NULL,
                    remote_event_id TEXT,
                    exported_at TEXT NOT NULL,
                    PRIMARY KEY (uid, destination_kind, destination_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cached_posts (
                    collection_name TEXT NOT NULL,
                    media_pk TEXT NOT NULL,
                    post_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (collection_name, media_pk)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cached_media (
                    collection_name TEXT NOT NULL,
                    media_pk TEXT NOT NULL,
                    media_kind TEXT NOT NULL,
                    media_index INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    local_path TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    PRIMARY KEY (collection_name, media_pk, media_kind, media_index),
                    FOREIGN KEY (collection_name, media_pk)
                        REFERENCES cached_posts(collection_name, media_pk)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cached_extractions (
                    media_pk TEXT NOT NULL,
                    model_signature TEXT NOT NULL,
                    source_media_kind TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    extracted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (media_pk, model_signature, source_media_kind)
                )
                """
            )

    def stable_uid(self, media_pk: str, event_index: int, title: str, start: str) -> str:
        digest = hashlib.sha256(f"{media_pk}|{event_index}|{title}|{start}".encode()).hexdigest()
        return f"instacalendar-{digest[:32]}@instacalendar"

    def extraction_model_signature(
        self, *, text_model: str, vision_model: str, video_model: str
    ) -> str:
        return json.dumps(
            {
                "text": text_model,
                "vision": vision_model,
                "video": video_model,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def record_extraction_result(
        self,
        *,
        media_pk: str,
        model_signature: str,
        source_media_kind: str,
        result: ExtractionResult,
        extracted_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cached_extractions (
                    media_pk, model_signature, source_media_kind, result_json, extracted_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(media_pk, model_signature, source_media_kind) DO UPDATE SET
                    result_json = excluded.result_json,
                    extracted_at = excluded.extracted_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    media_pk,
                    model_signature,
                    source_media_kind,
                    result.model_dump_json(),
                    extracted_at.isoformat(),
                ),
            )

    def get_extraction_result(
        self,
        *,
        media_pk: str,
        model_signature: str,
        source_media_kind: str,
        event_cache_key: str,
    ) -> ExtractionResult | None:
        if event_cache_key not in EVENT_CACHE_KEYS:
            raise ValueError(f"Unsupported event cache key: {event_cache_key}")
        clauses = ["media_pk = ?"]
        params: list[str] = [media_pk]
        if "model" in event_cache_key:
            clauses.append("model_signature = ?")
            params.append(model_signature)
        if "media" in event_cache_key:
            clauses.append("source_media_kind = ?")
            params.append(source_media_kind)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT result_json
                FROM cached_extractions
                WHERE {where}
                ORDER BY extracted_at DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        if row is None:
            return None
        return ExtractionResult.model_validate_json(row[0])

    def record_review(self, media_pk: str, event_index: int, decision: str, uid: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reviews (media_pk, event_index, decision, uid)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(media_pk, event_index) DO UPDATE SET
                    decision = excluded.decision,
                    uid = excluded.uid,
                    reviewed_at = CURRENT_TIMESTAMP
                """,
                (media_pk, event_index, decision, uid),
            )

    def record_export(
        self,
        *,
        uid: str,
        media_pk: str,
        event_index: int,
        destination_kind: str,
        destination_id: str,
        remote_event_id: str | None,
        exported_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO exports (
                    uid, media_pk, event_index, destination_kind, destination_id,
                    remote_event_id, exported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid, destination_kind, destination_id) DO UPDATE SET
                    remote_event_id = excluded.remote_event_id,
                    exported_at = excluded.exported_at
                """,
                (
                    uid,
                    media_pk,
                    event_index,
                    destination_kind,
                    destination_id,
                    remote_event_id,
                    exported_at.isoformat(),
                ),
            )

    def has_export(self, uid: str, destination_kind: str, destination_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM exports
                WHERE uid = ? AND destination_kind = ? AND destination_id = ?
                """,
                (uid, destination_kind, destination_id),
            ).fetchone()
        return row is not None

    def list_exports(self) -> list[CachedExport]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT uid, media_pk, event_index, destination_kind, destination_id,
                       remote_event_id, exported_at
                FROM exports
                ORDER BY exported_at DESC
                """
            ).fetchall()
        return [CachedExport(*row) for row in rows]

    def list_cached_extractions(self) -> list[CachedExtraction]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT media_pk, model_signature, source_media_kind,
                       result_json, extracted_at
                FROM cached_extractions
                ORDER BY extracted_at DESC
                """
            ).fetchall()
        extractions = []
        for media_pk, model_signature, source_media_kind, result_json, extracted_at in rows:
            data = json.loads(result_json)
            events = data.get("events") or []
            event_titles = [e.get("title") or "" for e in events]
            extractions.append(
                CachedExtraction(
                    media_pk=media_pk,
                    model_signature=model_signature,
                    source_media_kind=source_media_kind,
                    extracted_at=extracted_at,
                    status=data.get("status") or "",
                    event_count=len(events),
                    event_titles=event_titles,
                    warnings_count=len(data.get("warnings") or []),
                )
            )
        return extractions

    def upsert_cached_post(
        self,
        *,
        collection_name: str,
        post: InstagramPost,
        fetched_at: datetime,
        media: list[CachedMedia],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cached_posts (collection_name, media_pk, post_json, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(collection_name, media_pk) DO UPDATE SET
                    post_json = excluded.post_json,
                    fetched_at = excluded.fetched_at
                """,
                (
                    collection_name,
                    post.media_pk,
                    post.model_dump_json(),
                    fetched_at.isoformat(),
                ),
            )
            conn.execute(
                """
                DELETE FROM cached_media
                WHERE collection_name = ? AND media_pk = ?
                """,
                (collection_name, post.media_pk),
            )
            conn.executemany(
                """
                INSERT INTO cached_media (
                    collection_name, media_pk, media_kind, media_index, source_url,
                    local_path, status, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.collection_name,
                        item.media_pk,
                        item.media_kind,
                        item.media_index,
                        item.source_url,
                        item.local_path,
                        item.status,
                        item.error,
                    )
                    for item in media
                ],
            )

    def list_cached_collections(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT collection_name FROM cached_posts ORDER BY collection_name"
            ).fetchall()
        return [row[0] for row in rows]

    def load_cached_posts(self, collection_name: str) -> list[InstagramPost]:
        with self._connect() as conn:
            post_rows = conn.execute(
                """
                SELECT media_pk, post_json
                FROM cached_posts
                WHERE collection_name = ?
                ORDER BY rowid
                """,
                (collection_name,),
            ).fetchall()
            media_rows = conn.execute(
                """
                SELECT media_pk, media_kind, media_index, source_url, local_path, status
                FROM cached_media
                WHERE collection_name = ?
                ORDER BY media_pk, media_kind, media_index
                """,
                (collection_name,),
            ).fetchall()
        media_by_post: dict[str, list[tuple[str, int, str, str | None, str]]] = {}
        for media_pk, media_kind, media_index, source_url, local_path, status in media_rows:
            media_by_post.setdefault(media_pk, []).append(
                (media_kind, media_index, source_url, local_path, status)
            )

        posts = []
        for media_pk, post_json in post_rows:
            post = InstagramPost.model_validate_json(post_json)
            images: list[ImageReference] = []
            videos: list[VideoReference] = []
            for media_kind, _index, source_url, local_path, status in media_by_post.get(
                media_pk, []
            ):
                uri = local_path if status == "cached" and local_path else source_url
                if media_kind == "image":
                    images.append(ImageReference(uri=uri))
                elif media_kind == "video":
                    videos.append(VideoReference(uri=uri))
            posts.append(post.model_copy(update={"images": images, "videos": videos}))
        return posts

    def list_cached_posts(self, collection_name: str | None = None) -> list[CachedPostSummary]:
        params: tuple[str, ...] = ()
        where = ""
        if collection_name is not None:
            where = "WHERE p.collection_name = ?"
            params = (collection_name,)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    p.collection_name,
                    p.media_pk,
                    p.post_json,
                    p.fetched_at,
                    SUM(CASE WHEN m.media_kind = 'image' AND m.status = 'cached'
                        THEN 1 ELSE 0 END) AS cached_images,
                    SUM(CASE WHEN m.media_kind = 'video' AND m.status = 'cached'
                        THEN 1 ELSE 0 END) AS cached_videos,
                    SUM(CASE WHEN m.status != 'cached'
                        THEN 1 ELSE 0 END) AS missing_media
                FROM cached_posts p
                LEFT JOIN cached_media m
                    ON p.collection_name = m.collection_name
                    AND p.media_pk = m.media_pk
                {where}
                GROUP BY p.collection_name, p.media_pk, p.post_json, p.fetched_at
                ORDER BY p.fetched_at DESC, p.collection_name, p.media_pk
                """,
                params,
            ).fetchall()
        summaries = []
        for (
            row_collection_name,
            media_pk,
            post_json,
            fetched_at,
            cached_images,
            cached_videos,
            missing_media,
        ) in rows:
            data = json.loads(post_json)
            caption = data.get("caption") or ""
            summaries.append(
                CachedPostSummary(
                    collection_name=row_collection_name,
                    media_pk=media_pk,
                    shortcode=data.get("shortcode"),
                    taken_at=data.get("taken_at"),
                    media_kind=data.get("media_kind") or "",
                    fetched_at=fetched_at,
                    cached_images=int(cached_images or 0),
                    cached_videos=int(cached_videos or 0),
                    missing_media=int(missing_media or 0),
                    caption_preview=caption[:80],
                )
            )
        return summaries

    def cache_info(self, media_dir: Path) -> CacheInfo:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT collection_name, media_kind, local_path, status
                FROM cached_media
                ORDER BY collection_name, media_kind, media_index
                """
            ).fetchall()

        collection_counts: dict[str, dict[str, int]] = {}
        collection_sizes: dict[str, int] = {}
        collection_missing: dict[str, int] = {}
        total_counts: dict[str, int] = {}
        total_missing = 0
        seen_paths: set[Path] = set()

        for collection_name, media_kind, local_path, status in rows:
            collection_counts.setdefault(collection_name, {})
            collection_sizes.setdefault(collection_name, 0)
            collection_missing.setdefault(collection_name, 0)
            if status != "cached" or not local_path:
                collection_missing[collection_name] += 1
                total_missing += 1
                continue

            path = Path(local_path)
            if not path.exists() or not path.is_file():
                collection_missing[collection_name] += 1
                total_missing += 1
                continue

            collection_counts[collection_name][media_kind] = (
                collection_counts[collection_name].get(media_kind, 0) + 1
            )
            total_counts[media_kind] = total_counts.get(media_kind, 0) + 1
            if path not in seen_paths:
                size = path.stat().st_size
                collection_sizes[collection_name] += size
                seen_paths.add(path)

        media_size_bytes = self._directory_size(media_dir)
        database_size_bytes = self.path.stat().st_size if self.path.exists() else 0
        collection_names = set(collection_counts) | set(collection_sizes) | set(collection_missing)
        collections = [
            CacheCollectionInfo(
                collection_name=collection_name,
                file_counts=collection_counts.get(collection_name, {}),
                size_bytes=collection_sizes.get(collection_name, 0),
                missing_media_count=collection_missing.get(collection_name, 0),
            )
            for collection_name in sorted(collection_names)
        ]
        return CacheInfo(
            cache_file=self.path,
            media_dir=media_dir,
            database_size_bytes=database_size_bytes,
            media_size_bytes=media_size_bytes,
            total_size_bytes=database_size_bytes + media_size_bytes,
            total_file_counts=total_counts,
            missing_media_count=total_missing,
            collections=collections,
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _directory_size(self, path: Path) -> int:
        if not path.exists():
            return 0
        return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
