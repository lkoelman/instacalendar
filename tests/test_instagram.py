from datetime import datetime
from types import SimpleNamespace

import pytest
from instagrapi.exceptions import ClientError

from instacalendar.instagram import InstagramAdapter, InstagramFetchError, LiveInstagramClient


def _media(pk: int) -> SimpleNamespace:
    return SimpleNamespace(
        pk=pk,
        code=f"code-{pk}",
        caption_text="May 3 at The Room",
        taken_at=datetime(2026, 4, 1, 12, 0),
        media_type=1,
        thumbnail_url=None,
        resources=[],
        location=None,
    )


def test_instagram_adapter_maps_media_object_to_post_contract() -> None:
    media = SimpleNamespace(
        pk=123,
        code="abc",
        caption_text="May 3 at The Room",
        taken_at=datetime(2026, 4, 1, 12, 0),
        media_type=1,
        thumbnail_url="https://cdn.example/post.jpg",
        resources=[],
        location=SimpleNamespace(name="The Room", address="1 Main St"),
    )

    post = InstagramAdapter(client=None).map_media(media)

    assert post.media_pk == "123"
    assert post.source_url == "https://www.instagram.com/p/abc/"
    assert post.taken_at is not None
    assert post.taken_at.tzinfo is not None
    assert post.location_name == "The Room"
    assert post.images[0].uri == "https://cdn.example/post.jpg"


def test_instagram_adapter_maps_video_and_carousel_resources() -> None:
    media = SimpleNamespace(
        pk=123,
        code="abc",
        caption_text="May 3 at The Room",
        taken_at=datetime(2026, 4, 1, 12, 0),
        media_type=8,
        thumbnail_url="https://cdn.example/post.jpg",
        video_url="https://cdn.example/post.mp4",
        resources=[
            SimpleNamespace(
                thumbnail_url="https://cdn.example/slide.jpg",
                video_url=None,
                media_type=1,
            ),
            SimpleNamespace(
                thumbnail_url="https://cdn.example/video-thumb.jpg",
                video_url="https://cdn.example/slide.mp4",
                media_type=2,
            ),
        ],
        location=None,
    )

    post = InstagramAdapter(client=None).map_media(media)

    assert [image.uri for image in post.images] == [
        "https://cdn.example/post.jpg",
        "https://cdn.example/slide.jpg",
        "https://cdn.example/video-thumb.jpg",
    ]
    assert [video.uri for video in post.videos] == [
        "https://cdn.example/post.mp4",
        "https://cdn.example/slide.mp4",
    ]


def test_live_instagram_client_fetches_all_collection_posts_by_collection_pk() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.requested_name = None
            self.requested_collection_pk = None
            self.requested_max_ids = []

        def collection_pk_by_name(self, name: str) -> str:
            self.requested_name = name
            return "collection-123"

        def collection_medias_v1_chunk(
            self, collection_pk: str, *, max_id: str = ""
        ) -> tuple[list[SimpleNamespace], str]:
            self.requested_collection_pk = collection_pk
            self.requested_max_ids.append(max_id)
            if not max_id:
                return [_media(123)], "next-page"
            return [_media(456)], ""

    fake_client = FakeClient()
    client = LiveInstagramClient.__new__(LiveInstagramClient)
    client.client = fake_client
    client.adapter = InstagramAdapter(fake_client)

    posts = client.fetch_collection_posts("Concerts")

    assert fake_client.requested_name == "Concerts"
    assert fake_client.requested_collection_pk == "collection-123"
    assert fake_client.requested_max_ids == ["", "next-page"]
    assert [post.media_pk for post in posts] == ["123", "456"]


def test_live_instagram_client_returns_partial_posts_when_later_page_keeps_failing() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.requested_max_ids = []

        def collection_pk_by_name(self, name: str) -> str:
            return "collection-123"

        def collection_medias_v1_chunk(
            self, collection_pk: str, *, max_id: str = ""
        ) -> tuple[list[SimpleNamespace], str]:
            self.requested_max_ids.append(max_id)
            if not max_id:
                return [_media(123)], "next-page"
            raise ClientError("572 Server Error")

    fake_client = FakeClient()
    client = LiveInstagramClient.__new__(LiveInstagramClient)
    client.client = fake_client
    client.adapter = InstagramAdapter(fake_client)
    client.fetch_retry_delay_seconds = 0

    posts = client.fetch_collection_posts("Concerts")

    assert fake_client.requested_max_ids == ["", "next-page", "next-page", "next-page"]
    assert [post.media_pk for post in posts] == ["123"]


def test_live_instagram_client_raises_clear_error_when_first_page_keeps_failing() -> None:
    class FakeClient:
        def collection_pk_by_name(self, name: str) -> str:
            return "collection-123"

        def collection_medias_v1_chunk(
            self, collection_pk: str, *, max_id: str = ""
        ) -> tuple[list[SimpleNamespace], str]:
            raise ClientError("572 Server Error")

    client = LiveInstagramClient.__new__(LiveInstagramClient)
    client.client = FakeClient()
    client.adapter = InstagramAdapter(client.client)
    client.fetch_retry_delay_seconds = 0

    with pytest.raises(
        InstagramFetchError,
        match="Could not fetch posts from Instagram collection",
    ):
        client.fetch_collection_posts("Concerts")
