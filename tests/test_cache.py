from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from instacalendar.cache import Cache, CachedMedia
from instacalendar.models import ImageReference, InstagramPost, VideoReference


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


def test_cache_round_trips_posts_and_media(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()
    post = InstagramPost(
        media_pk="media-1",
        shortcode="abc",
        caption="May 3 at The Room",
        taken_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
        media_kind="8",
        location_name="The Room",
        images=[ImageReference(uri="https://cdn.example/photo.jpg")],
        videos=[VideoReference(uri="https://cdn.example/video.mp4")],
    )

    cache.upsert_cached_post(
        collection_name="Concerts",
        post=post,
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("UTC")),
        media=[
            CachedMedia(
                collection_name="Concerts",
                media_pk="media-1",
                media_kind="image",
                media_index=0,
                source_url="https://cdn.example/photo.jpg",
                local_path=str(tmp_path / "media" / "photo.jpg"),
                status="cached",
                error=None,
            ),
            CachedMedia(
                collection_name="Concerts",
                media_pk="media-1",
                media_kind="video",
                media_index=0,
                source_url="https://cdn.example/video.mp4",
                local_path=None,
                status="failed",
                error="timeout",
            ),
        ],
    )

    loaded = cache.load_cached_posts("Concerts")
    assert loaded == [
        InstagramPost(
            media_pk="media-1",
            shortcode="abc",
            caption="May 3 at The Room",
            taken_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
            media_kind="8",
            location_name="The Room",
            images=[ImageReference(uri=str(tmp_path / "media" / "photo.jpg"))],
            videos=[VideoReference(uri="https://cdn.example/video.mp4")],
        )
    ]
    summaries = cache.list_cached_posts()
    assert summaries[0].collection_name == "Concerts"
    assert summaries[0].media_pk == "media-1"
    assert summaries[0].cached_images == 1
    assert summaries[0].cached_videos == 0
    assert summaries[0].missing_media == 1
    assert summaries[0].caption_preview == "May 3 at The Room"


def test_cache_lists_cached_collections(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()

    for collection in ["Concerts", "Art"]:
        cache.upsert_cached_post(
            collection_name=collection,
            post=InstagramPost(media_pk=collection, caption="", media_kind="1"),
            fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("UTC")),
            media=[],
        )

    assert cache.list_cached_collections() == ["Art", "Concerts"]


def test_cache_info_summarizes_files_and_size_by_collection(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()
    media_dir = tmp_path / "media"
    concert_image = media_dir / "Concerts" / "1" / "image-0.jpg"
    concert_video = media_dir / "Concerts" / "1" / "video-0.mp4"
    art_image = media_dir / "Art" / "2" / "image-0.png"
    concert_image.parent.mkdir(parents=True)
    concert_image.write_bytes(b"i" * 10)
    concert_video.write_bytes(b"v" * 30)
    art_image.parent.mkdir(parents=True)
    art_image.write_bytes(b"a" * 5)

    cache.upsert_cached_post(
        collection_name="Concerts",
        post=InstagramPost(media_pk="1", caption="", media_kind="8"),
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("UTC")),
        media=[
            CachedMedia(
                collection_name="Concerts",
                media_pk="1",
                media_kind="image",
                media_index=0,
                source_url="https://cdn.example/image.jpg",
                local_path=str(concert_image),
                status="cached",
                error=None,
            ),
            CachedMedia(
                collection_name="Concerts",
                media_pk="1",
                media_kind="video",
                media_index=0,
                source_url="https://cdn.example/video.mp4",
                local_path=str(concert_video),
                status="cached",
                error=None,
            ),
            CachedMedia(
                collection_name="Concerts",
                media_pk="1",
                media_kind="video",
                media_index=1,
                source_url="https://cdn.example/missing.mp4",
                local_path=None,
                status="failed",
                error="timeout",
            ),
        ],
    )
    cache.upsert_cached_post(
        collection_name="Art",
        post=InstagramPost(media_pk="2", caption="", media_kind="1"),
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("UTC")),
        media=[
            CachedMedia(
                collection_name="Art",
                media_pk="2",
                media_kind="image",
                media_index=0,
                source_url="https://cdn.example/art.png",
                local_path=str(art_image),
                status="cached",
                error=None,
            )
        ],
    )

    info = cache.cache_info(media_dir)

    assert info.cache_file == tmp_path / "cache.sqlite3"
    assert info.media_dir == media_dir
    assert info.database_size_bytes > 0
    assert info.media_size_bytes == 45
    assert info.total_size_bytes == info.database_size_bytes + 45
    assert info.total_file_counts == {"image": 2, "video": 1}
    assert info.missing_media_count == 1
    assert [(item.collection_name, item.size_bytes) for item in info.collections] == [
        ("Art", 5),
        ("Concerts", 40),
    ]
    assert info.collections[1].file_counts == {"image": 1, "video": 1}
    assert info.collections[1].missing_media_count == 1
