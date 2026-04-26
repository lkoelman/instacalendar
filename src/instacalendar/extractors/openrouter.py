from __future__ import annotations

import json
import mimetypes
from base64 import b64encode
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from instacalendar.models import EventDraft, ExtractionResult, InstagramPost

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        text_model: str,
        vision_model: str,
        video_model: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.text_model = text_model
        self.vision_model = vision_model
        self.video_model = video_model or vision_model
        self.client = client or httpx.Client(timeout=60)

    def extract(
        self,
        post: InstagramPost,
        *,
        status_callback: Callable[[str], None] | None = None,
    ) -> ExtractionResult:
        if status_callback:
            status_callback("Interpreting post text")
        result = self._call_model(post, self.text_model, include_images=False, include_videos=False)
        if self._is_confident_event(result):
            return result
        if post.images:
            if status_callback:
                status_callback("Falling back to image")
                status_callback("Interpreting image")
            result = self._call_model(
                post,
                self.vision_model,
                include_images=True,
                include_videos=False,
            )
            if self._is_confident_event(result):
                return result
        elif status_callback:
            status_callback("No image fallback available")
        if self._local_video_uris(post):
            if status_callback:
                status_callback("Falling back to video")
                status_callback("Interpreting video")
            return self._call_model(
                post,
                self.video_model,
                include_images=False,
                include_videos=True,
            )
        if status_callback:
            status_callback("No video fallback available")
        return result

    def _call_model(
        self, post: InstagramPost, model: str, *, include_images: bool, include_videos: bool
    ) -> ExtractionResult:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract calendar event data from Instagram posts. "
                        "Return only JSON with status, confidence, events, and warnings. "
                        "status must be event, not_event, or needs_review."
                    ),
                },
                {
                    "role": "user",
                    "content": self._user_content(
                        post,
                        include_images=include_images,
                        include_videos=include_videos,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        response = self.client.post(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/lkoelman/instacalendar",
                "X-Title": "instacalendar",
            },
            json=payload,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._parse_result(content, model)

    def _user_content(
        self, post: InstagramPost, *, include_images: bool, include_videos: bool
    ) -> str | list[dict[str, Any]]:
        text = {
            "media_pk": post.media_pk,
            "source_url": post.source_url,
            "caption": post.caption,
            "taken_at": post.taken_at.isoformat() if post.taken_at else None,
            "location_name": post.location_name,
            "location_address": post.location_address,
        }
        prompt = f"Instagram post metadata:\n{json.dumps(text, ensure_ascii=False)}"
        if not include_images and not include_videos:
            return prompt
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if include_images:
            for image in post.images:
                content.append(
                    {"type": "image_url", "image_url": {"url": self._image_url(image.uri)}}
                )
        if include_videos:
            for uri in self._local_video_uris(post):
                content.append({"type": "video_url", "video_url": {"url": self._data_url(uri)}})
        return content

    def _image_url(self, uri: str) -> str:
        path = Path(uri)
        if not path.exists():
            return uri
        return self._data_url(uri)

    def _local_video_uris(self, post: InstagramPost) -> list[str]:
        return [video.uri for video in post.videos if Path(video.uri).exists()]

    def _data_url(self, uri: str) -> str:
        path = Path(uri)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return f"data:{mime_type};base64,{b64encode(path.read_bytes()).decode()}"

    def _is_confident_event(self, result: ExtractionResult) -> bool:
        if result.status != "event" or not result.events:
            return False
        return min((event.confidence or result.confidence or 0) for event in result.events) >= 0.7

    def _parse_result(self, content: str, model: str) -> ExtractionResult:
        data = json.loads(content)
        events = [EventDraft.model_validate(event) for event in data.get("events", [])]
        return ExtractionResult(
            status=data.get("status", "needs_review"),
            events=events,
            model_ids=[model],
            confidence=data.get("confidence"),
            warnings=data.get("warnings", []),
        )
