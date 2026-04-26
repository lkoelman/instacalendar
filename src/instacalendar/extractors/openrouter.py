from __future__ import annotations

import json
import mimetypes
from base64 import b64encode
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import litellm
from pydantic import BaseModel, Field

from instacalendar.models import EventDraft, ExtractionResult, InstagramPost

OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/lkoelman/instacalendar",
    "X-Title": "instacalendar",
}


@dataclass(frozen=True)
class ModelUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None


class ExtractionResponse(BaseModel):
    status: Literal["event", "not_event", "needs_review"]
    confidence: float | None = None
    events: list[EventDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OpenRouterExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        text_model: str,
        vision_model: str,
        video_model: str | None = None,
        completion_func: Callable[..., Any] | None = None,
        cost_func: Callable[..., float | None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.text_model = text_model
        self.vision_model = vision_model
        self.video_model = video_model or vision_model
        self.completion_func = completion_func or litellm.completion
        self.cost_func = cost_func or litellm.completion_cost

    def extract(
        self,
        post: InstagramPost,
        *,
        status_callback: Callable[[str], None] | None = None,
        usage_callback: Callable[[ModelUsage], None] | None = None,
    ) -> ExtractionResult:
        if status_callback:
            status_callback("Interpreting post text")
        result = self._call_model(
            post,
            self.text_model,
            include_images=False,
            include_videos=False,
            usage_callback=usage_callback,
        )
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
                usage_callback=usage_callback,
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
                usage_callback=usage_callback,
            )
        if status_callback:
            status_callback("No video fallback available")
        return result

    def _call_model(
        self,
        post: InstagramPost,
        model: str,
        *,
        include_images: bool,
        include_videos: bool,
        usage_callback: Callable[[ModelUsage], None] | None,
    ) -> ExtractionResult:
        response = self.completion_func(
            model=self._litellm_model(model),
            messages=[
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
            response_format=ExtractionResponse,
            provider={"require_parameters": True},
            temperature=0,
            api_key=self.api_key,
            extra_headers=OPENROUTER_HEADERS,
        )
        if usage_callback:
            usage_callback(self._usage_from_response(response, model))
        return self._parse_result(response, model)

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

    def _litellm_model(self, model: str) -> str:
        if model.startswith("openrouter/"):
            return model
        return f"openrouter/{model}"

    def _parse_result(self, response: Any, model: str) -> ExtractionResult:
        parsed = self._message_field(response, "parsed")
        if parsed is None:
            content = self._message_field(response, "content")
            if isinstance(content, str):
                parsed = ExtractionResponse.model_validate_json(content)
            else:
                parsed = ExtractionResponse.model_validate(content)
        elif not isinstance(parsed, ExtractionResponse):
            parsed = ExtractionResponse.model_validate(parsed)
        return ExtractionResult(
            status=parsed.status,
            events=parsed.events,
            model_ids=[model],
            confidence=parsed.confidence,
            warnings=parsed.warnings,
        )

    def _message_field(self, response: Any, field: str) -> Any:
        choice = self._index(response, "choices", 0)
        message = self._get(choice, "message")
        return self._get(message, field)

    def _usage_from_response(self, response: Any, model: str) -> ModelUsage:
        usage = self._get(response, "usage") or {}
        prompt_tokens = int(self._get(usage, "prompt_tokens") or 0)
        completion_tokens = int(self._get(usage, "completion_tokens") or 0)
        total_tokens = int(self._get(usage, "total_tokens") or prompt_tokens + completion_tokens)
        return ModelUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=self._response_cost(response, model),
        )

    def _response_cost(self, response: Any, model: str) -> float | None:
        hidden_params = self._get(response, "_hidden_params") or {}
        cost = self._get(hidden_params, "response_cost")
        if cost is None:
            cost = self._get(response, "response_cost")
        if cost is None:
            try:
                cost = self.cost_func(
                    completion_response=response,
                    model=self._litellm_model(model),
                )
            except Exception:
                return None
        return float(cost) if cost is not None else None

    def _index(self, value: Any, field: str, index: int) -> Any:
        sequence = self._get(value, field) or []
        return sequence[index]

    def _get(self, value: Any, field: str) -> Any:
        if isinstance(value, dict):
            return value.get(field)
        return getattr(value, field, None)
