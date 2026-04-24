from __future__ import annotations

from datetime import UTC
from typing import Any

from instacalendar.models import ImageReference, InstagramPost


class InstagramAdapter:
    def __init__(self, client: Any) -> None:
        self.client = client

    def map_media(self, media: Any) -> InstagramPost:
        caption = getattr(media, "caption_text", None) or getattr(media, "caption", "") or ""
        taken_at = getattr(media, "taken_at", None)
        if taken_at is not None and taken_at.tzinfo is None:
            taken_at = taken_at.replace(tzinfo=UTC)
        images = []
        thumbnail_url = getattr(media, "thumbnail_url", None)
        if thumbnail_url:
            images.append(ImageReference(uri=str(thumbnail_url)))
        resources = getattr(media, "resources", None) or []
        for resource in resources:
            url = getattr(resource, "thumbnail_url", None)
            if url:
                images.append(ImageReference(uri=str(url)))
        location = getattr(media, "location", None)
        return InstagramPost(
            media_pk=str(media.pk),
            shortcode=getattr(media, "code", None),
            caption=caption,
            taken_at=taken_at,
            media_kind=str(getattr(media, "media_type", "unknown")),
            location_name=getattr(location, "name", None) if location else None,
            location_address=getattr(location, "address", None) if location else None,
            images=images,
        )


class LiveInstagramClient:
    def __init__(self, username: str, password: str, session_file) -> None:
        from instagrapi import Client

        self.username = username
        self.password = password
        self.session_file = session_file
        self.client = Client()
        self.adapter = InstagramAdapter(self.client)

    def authenticate(self) -> None:
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        if self.session_file.exists():
            self.client.load_settings(str(self.session_file))
        self.client.login(self.username, self.password)
        self.client.dump_settings(str(self.session_file))

    def list_collections(self) -> list[str]:
        collections = self.client.collections()
        names = [getattr(collection, "name", None) for collection in collections]
        return [name for name in names if name]

    def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
        medias = self.client.collection_medias_by_name(collection_name, amount=0)
        return [self.adapter.map_media(media) for media in medias]
