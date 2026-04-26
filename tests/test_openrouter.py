import base64
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import respx

from instacalendar.extractors.openrouter import OpenRouterExtractor
from instacalendar.models import ImageReference, InstagramPost, VideoReference


@respx.mock
def test_openrouter_uses_text_model_first_and_returns_event() -> None:
    model_response = {
        "status": "event",
        "confidence": 0.91,
        "events": [
            {
                "title": "Live Set",
                "start": "2026-05-03T20:00:00-04:00",
                "timezone": "America/New_York",
                "source_url": "https://www.instagram.com/p/abc/",
            }
        ],
        "warnings": [],
    }
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(model_response),
                        }
                    }
                ]
            },
        )
    )
    post = InstagramPost(
        media_pk="1",
        shortcode="abc",
        caption="Live Set May 3 8pm",
        taken_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
        media_kind="image",
    )

    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        client=httpx.Client(),
    ).extract(post)

    assert result.status == "event"
    assert result.events[0].title == "Live Set"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer key"
    assert '"model":"text-model"' in request.content.decode()


@respx.mock
def test_openrouter_reports_text_interpretation_status() -> None:
    model_response = {
        "status": "event",
        "confidence": 0.91,
        "events": [
            {
                "title": "Live Set",
                "start": "2026-05-03T20:00:00-04:00",
                "source_url": "https://www.instagram.com/p/abc/",
            }
        ],
        "warnings": [],
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_response)}}]},
        )
    )
    messages: list[str] = []

    OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        client=httpx.Client(),
    ).extract(
        InstagramPost(media_pk="1", shortcode="abc", caption="Live Set", media_kind="image"),
        status_callback=messages.append,
    )

    assert messages == ["Interpreting post text"]


@respx.mock
def test_openrouter_encodes_local_cached_images_for_vision_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_bytes = b"fake image"
    image_path.write_bytes(image_bytes)
    text_response = {
        "status": "needs_review",
        "confidence": 0.2,
        "events": [],
        "warnings": [],
    }
    vision_response = {
        "status": "event",
        "confidence": 0.91,
        "events": [
            {
                "title": "Live Set",
                "start": "2026-05-03T20:00:00-04:00",
                "source_url": "https://www.instagram.com/p/abc/",
            }
        ],
        "warnings": [],
    }
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(text_response)}}]},
            ),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(vision_response)}}]},
            ),
        ]
    )
    post = InstagramPost(
        media_pk="1",
        shortcode="abc",
        caption="Live Set May 3",
        media_kind="image",
        images=[ImageReference(uri=str(image_path))],
    )

    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        client=httpx.Client(),
    ).extract(post)

    assert result.status == "event"
    vision_payload = json.loads(route.calls[1].request.content)
    image_url = vision_payload["messages"][1]["content"][1]["image_url"]["url"]
    assert image_url == f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"


@respx.mock
def test_openrouter_reports_image_fallback_statuses(tmp_path: Path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_path.write_bytes(b"fake image")
    text_response = {
        "status": "needs_review",
        "confidence": 0.2,
        "events": [],
        "warnings": [],
    }
    vision_response = {
        "status": "event",
        "confidence": 0.91,
        "events": [
            {
                "title": "Live Set",
                "start": "2026-05-03T20:00:00-04:00",
            }
        ],
        "warnings": [],
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(text_response)}}]},
            ),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(vision_response)}}]},
            ),
        ]
    )
    messages: list[str] = []

    OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        client=httpx.Client(),
    ).extract(
        InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set",
            media_kind="image",
            images=[ImageReference(uri=str(image_path))],
        ),
        status_callback=messages.append,
    )

    assert messages == [
        "Interpreting post text",
        "Falling back to image",
        "Interpreting image",
    ]


@respx.mock
def test_openrouter_encodes_local_cached_videos_for_final_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_path.write_bytes(b"fake image")
    video_path = tmp_path / "clip.mp4"
    video_bytes = b"fake video"
    video_path.write_bytes(video_bytes)
    inconclusive_response = {
        "status": "needs_review",
        "confidence": 0.2,
        "events": [],
        "warnings": [],
    }
    video_response = {
        "status": "event",
        "confidence": 0.91,
        "events": [
            {
                "title": "Live Set",
                "start": "2026-05-03T20:00:00-04:00",
            }
        ],
        "warnings": [],
    }
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(inconclusive_response)}}]},
            ),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(inconclusive_response)}}]},
            ),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(video_response)}}]},
            ),
        ]
    )
    messages: list[str] = []

    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        video_model="video-model",
        client=httpx.Client(),
    ).extract(
        InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set",
            media_kind="video",
            images=[ImageReference(uri=str(image_path))],
            videos=[VideoReference(uri=str(video_path))],
        ),
        status_callback=messages.append,
    )

    assert result.status == "event"
    video_payload = json.loads(route.calls[2].request.content)
    assert video_payload["model"] == "video-model"
    video_url = video_payload["messages"][1]["content"][1]["video_url"]["url"]
    assert video_url == f"data:video/mp4;base64,{base64.b64encode(video_bytes).decode()}"
    assert messages == [
        "Interpreting post text",
        "Falling back to image",
        "Interpreting image",
        "Falling back to video",
        "Interpreting video",
    ]


@respx.mock
def test_openrouter_skips_remote_video_urls() -> None:
    text_response = {
        "status": "needs_review",
        "confidence": 0.2,
        "events": [],
        "warnings": [],
    }
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(text_response)}}]},
        )
    )
    messages: list[str] = []

    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        video_model="video-model",
        client=httpx.Client(),
    ).extract(
        InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set",
            media_kind="video",
            videos=[VideoReference(uri="https://cdn.example/video.mp4")],
        ),
        status_callback=messages.append,
    )

    assert result.status == "needs_review"
    assert route.call_count == 1
    assert messages == [
        "Interpreting post text",
        "No image fallback available",
        "No video fallback available",
    ]


@respx.mock
def test_openrouter_uses_vision_model_for_video_when_no_video_model(tmp_path: Path) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video")
    text_response = {
        "status": "needs_review",
        "confidence": 0.2,
        "events": [],
        "warnings": [],
    }
    video_response = {
        "status": "event",
        "confidence": 0.91,
        "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
        "warnings": [],
    }
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(text_response)}}]},
            ),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(video_response)}}]},
            ),
        ]
    )

    OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        client=httpx.Client(),
    ).extract(
        InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set",
            media_kind="video",
            videos=[VideoReference(uri=str(video_path))],
        )
    )

    video_payload = json.loads(route.calls[1].request.content)
    assert video_payload["model"] == "vision-model"
