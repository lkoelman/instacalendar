from datetime import datetime
from types import SimpleNamespace

from instacalendar.instagram import InstagramAdapter


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
