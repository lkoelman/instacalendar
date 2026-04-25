from datetime import datetime
from types import SimpleNamespace

from instacalendar.instagram import InstagramAdapter, LiveInstagramClient


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


def test_live_instagram_client_fetches_all_collection_posts_by_collection_pk() -> None:
    media = SimpleNamespace(
        pk=123,
        code="abc",
        caption_text="May 3 at The Room",
        taken_at=datetime(2026, 4, 1, 12, 0),
        media_type=1,
        thumbnail_url=None,
        resources=[],
        location=None,
    )

    class FakeClient:
        def __init__(self) -> None:
            self.requested_name = None
            self.requested_collection_pk = None
            self.requested_amount = None

        def collection_pk_by_name(self, name: str) -> str:
            self.requested_name = name
            return "collection-123"

        def collection_medias(self, collection_pk: str, *, amount: int) -> list[SimpleNamespace]:
            self.requested_collection_pk = collection_pk
            self.requested_amount = amount
            return [media]

    fake_client = FakeClient()
    client = LiveInstagramClient.__new__(LiveInstagramClient)
    client.client = fake_client
    client.adapter = InstagramAdapter(fake_client)

    posts = client.fetch_collection_posts("Concerts")

    assert fake_client.requested_name == "Concerts"
    assert fake_client.requested_collection_pk == "collection-123"
    assert fake_client.requested_amount == 0
    assert [post.media_pk for post in posts] == ["123"]
