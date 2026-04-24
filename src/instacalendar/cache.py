from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class CachedExport:
    uid: str
    media_pk: str
    event_index: int
    destination_kind: str
    destination_id: str
    remote_event_id: str | None
    exported_at: str


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

    def stable_uid(self, media_pk: str, event_index: int, title: str, start: str) -> str:
        digest = hashlib.sha256(f"{media_pk}|{event_index}|{title}|{start}".encode()).hexdigest()
        return f"instacalendar-{digest[:32]}@instacalendar"

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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
