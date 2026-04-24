from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from instacalendar.cache import Cache


def test_cache_records_review_and_export_idempotently(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()

    uid = cache.stable_uid("media-1", 0, "Club Night", "2026-05-03T20:00:00")
    assert not cache.has_export(uid, "ics", "/tmp/events.ics")

    cache.record_review("media-1", 0, "approved", uid)
    cache.record_export(
        uid=uid,
        media_pk="media-1",
        event_index=0,
        destination_kind="ics",
        destination_id="/tmp/events.ics",
        remote_event_id=None,
        exported_at=datetime(2026, 5, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
    )
    cache.record_export(
        uid=uid,
        media_pk="media-1",
        event_index=0,
        destination_kind="ics",
        destination_id="/tmp/events.ics",
        remote_event_id=None,
        exported_at=datetime(2026, 5, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
    )

    assert cache.has_export(uid, "ics", "/tmp/events.ics")
    assert len(cache.list_exports()) == 1
