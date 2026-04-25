from __future__ import annotations

import logging
import time
from datetime import UTC
from typing import Any

from instagrapi.exceptions import ClientError

from instacalendar.models import ImageReference, InstagramPost, VideoReference

logger = logging.getLogger(__name__)


class InstagramFetchError(RuntimeError):
    pass


class InstagramAdapter:
    def __init__(self, client: Any) -> None:
        self.client = client

    def map_media(self, media: Any) -> InstagramPost:
        caption = getattr(media, "caption_text", None) or getattr(media, "caption", "") or ""
        taken_at = getattr(media, "taken_at", None)
        if taken_at is not None and taken_at.tzinfo is None:
            taken_at = taken_at.replace(tzinfo=UTC)
        images = []
        videos = []
        thumbnail_url = getattr(media, "thumbnail_url", None)
        if thumbnail_url:
            images.append(ImageReference(uri=str(thumbnail_url)))
        video_url = getattr(media, "video_url", None)
        if video_url:
            videos.append(VideoReference(uri=str(video_url)))
        resources = getattr(media, "resources", None) or []
        for resource in resources:
            url = getattr(resource, "thumbnail_url", None)
            if url:
                images.append(ImageReference(uri=str(url)))
            video_url = getattr(resource, "video_url", None)
            if video_url:
                videos.append(VideoReference(uri=str(video_url)))
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
            videos=videos,
        )


class LiveInstagramClient:
    def __init__(self, username: str, password: str, session_file) -> None:
        from instagrapi import Client

        self.username = username
        self.password = password
        self.session_file = session_file
        self.client = Client()
        self.adapter = InstagramAdapter(self.client)
        self.fetch_retries = 2
        self.fetch_retry_delay_seconds = 1.0

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
        collection_pk = self.client.collection_pk_by_name(collection_name)
        medias = []
        next_max_id = ""
        while True:
            try:
                items, next_max_id = self._fetch_collection_chunk(collection_pk, max_id=next_max_id)
            except ClientError as error:
                if medias:
                    logger.warning(
                        "Stopped fetching Instagram collection %s after %s posts: %s",
                        collection_name,
                        len(medias),
                        error,
                    )
                    break
                raise InstagramFetchError(
                    f"Could not fetch posts from Instagram collection {collection_name!r}: {error}"
                ) from error
            medias.extend(items)
            if not items or not next_max_id:
                break
        return [self.adapter.map_media(media) for media in medias]

    def _fetch_collection_chunk(self, collection_pk: str, *, max_id: str) -> tuple[list[Any], str]:
        retries = getattr(self, "fetch_retries", 2)
        delay_seconds = getattr(self, "fetch_retry_delay_seconds", 1.0)
        for attempt in range(retries + 1):
            try:
                return self.client.collection_medias_v1_chunk(collection_pk, max_id=max_id)
            except ClientError:
                if attempt >= retries:
                    raise
                if delay_seconds:
                    time.sleep(delay_seconds)
        raise AssertionError("unreachable")
