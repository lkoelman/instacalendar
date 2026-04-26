import base64
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import litellm
import pytest

from instacalendar.extractors.openrouter import OpenRouterExtractor
from instacalendar.models import ImageReference, InstagramPost, VideoReference


def _response(content: str, *, prompt_tokens: int = 0, completion_tokens: int = 0):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def test_openrouter_uses_litellm_text_model_first_and_returns_event() -> None:
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [
                {
                  "title": "Live Set",
                  "start": "2026-05-03T20:00:00-04:00",
                  "timezone": "America/New_York",
                  "source_url": "https://www.instagram.com/p/abc/"
                }
              ],
              "warnings": []
            }
            """,
            prompt_tokens=120,
            completion_tokens=30,
        )

    usages = []
    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        completion_func=completion,
        cost_func=lambda **kwargs: 0.0012,
    ).extract(
        InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set May 3 8pm",
            taken_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
            media_kind="image",
        ),
        usage_callback=usages.append,
    )

    assert result.status == "event"
    assert result.events[0].title == "Live Set"
    assert result.model_ids == ["text-model"]
    assert calls[0]["model"] == "openrouter/text-model"
    assert calls[0]["api_key"] == "key"
    assert calls[0]["response_format"].__name__ == "ExtractionResponse"
    assert calls[0]["provider"] == {"require_parameters": True}
    assert calls[0]["temperature"] == 0
    assert calls[0]["extra_headers"] == {
        "HTTP-Referer": "https://github.com/lkoelman/instacalendar",
        "X-Title": "instacalendar",
    }
    assert usages[0].model == "text-model"
    assert usages[0].prompt_tokens == 120
    assert usages[0].completion_tokens == 30
    assert usages[0].total_tokens == 150
    assert usages[0].estimated_cost_usd == 0.0012


def test_openrouter_prefixes_provider_style_model_ids_for_openrouter() -> None:
    calls = []

    OpenRouterExtractor(
        api_key="key",
        text_model="openai/gpt-4o-mini",
        vision_model="openai/gpt-4o",
        completion_func=lambda **kwargs: calls.append(kwargs)
        or _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """
        ),
        cost_func=lambda **kwargs: 0.0,
    ).extract(InstagramPost(media_pk="1", caption="Live Set", media_kind="image"))

    assert calls[0]["model"] == "openrouter/openai/gpt-4o-mini"


def test_openrouter_passes_openrouter_model_to_litellm_cost_fallback() -> None:
    cost_calls = []

    OpenRouterExtractor(
        api_key="key",
        text_model="qwen/qwen3.5-9b",
        vision_model="google/gemini-3-flash-preview",
        completion_func=lambda **kwargs: _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """,
            prompt_tokens=100,
            completion_tokens=20,
        ),
        cost_func=lambda **kwargs: cost_calls.append(kwargs) or 0.001,
    ).extract(
        InstagramPost(media_pk="1", caption="Live Set", media_kind="image"),
        usage_callback=lambda usage: None,
    )

    assert cost_calls[0]["model"] == "openrouter/qwen/qwen3.5-9b"


def test_openrouter_leaves_litellm_output_raw_without_diagnostics(capsys, monkeypatch) -> None:
    monkeypatch.delenv("INSTACALENDAR_DEBUG_LITELLM_OUTPUT", raising=False)

    def noisy_completion(**kwargs):
        print("Provider List: https://docs.litellm.ai/docs/providers")
        return _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """
        )

    OpenRouterExtractor(
        api_key="key",
        text_model="qwen/qwen3.5-9b",
        vision_model="google/gemini-3-flash-preview",
        completion_func=noisy_completion,
        cost_func=lambda **kwargs: 0.0,
    ).extract(InstagramPost(media_pk="1", caption="Live Set", media_kind="image"))

    captured = capsys.readouterr()
    assert "Provider List" in captured.out
    assert "instacalendar litellm-debug" not in captured.err


def test_openrouter_litellm_completion_treats_nitro_catalog_id_as_openrouter(
    capsys, monkeypatch
) -> None:
    monkeypatch.delenv("INSTACALENDAR_DEBUG_LITELLM_OUTPUT", raising=False)

    def completion(**kwargs):
        return litellm.completion(
            **kwargs,
            mock_response="""
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """,
        )

    result = OpenRouterExtractor(
        api_key="key",
        text_model="qwen/qwen3.5-9b:nitro",
        vision_model="google/gemini-3-flash-preview",
        completion_func=completion,
        cost_func=lambda **kwargs: 0.0,
    ).extract(InstagramPost(media_pk="1", caption="Live Set", media_kind="image"))

    time.sleep(0.5)
    captured = capsys.readouterr()
    assert result.status == "event"
    assert result.model_ids == ["qwen/qwen3.5-9b:nitro"]
    assert "Provider List" not in captured.out
    assert "Provider List" not in captured.err


def test_openrouter_tags_litellm_cost_fallback_output_when_diagnostics_enabled(
    capsys, monkeypatch
) -> None:
    monkeypatch.setenv("INSTACALENDAR_DEBUG_LITELLM_OUTPUT", "1")

    def noisy_cost(**kwargs):
        print("Provider List: https://docs.litellm.ai/docs/providers")
        raise RuntimeError("unable to infer provider")

    usages = []
    result = OpenRouterExtractor(
        api_key="key",
        text_model="qwen/qwen3.5-9b",
        vision_model="google/gemini-3-flash-preview",
        completion_func=lambda **kwargs: _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """,
            prompt_tokens=100,
            completion_tokens=20,
        ),
        cost_func=noisy_cost,
    ).extract(
        InstagramPost(media_pk="1", caption="Live Set", media_kind="image"),
        usage_callback=usages.append,
    )

    captured = capsys.readouterr()
    assert result.status == "event"
    assert usages[0].estimated_cost_usd is None
    assert captured.out == ""
    assert "captured stdout from completion_cost configured_model=qwen/qwen3.5-9b" in (
        captured.err
    )
    assert "completion_cost configured_model=qwen/qwen3.5-9b" in captured.err
    assert "stdout> Provider List: https://docs.litellm.ai/docs/providers" in captured.err


def test_openrouter_tags_litellm_completion_output_when_diagnostics_enabled(
    capsys, monkeypatch
) -> None:
    monkeypatch.setenv("INSTACALENDAR_DEBUG_LITELLM_OUTPUT", "1")

    def noisy_completion(**kwargs):
        print("Provider List: https://docs.litellm.ai/docs/providers")
        return _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """
        )

    result = OpenRouterExtractor(
        api_key="key",
        text_model="qwen/qwen3.5-9b",
        vision_model="google/gemini-3-flash-preview",
        completion_func=noisy_completion,
        cost_func=lambda **kwargs: 0.0,
    ).extract(InstagramPost(media_pk="1", caption="Live Set", media_kind="image"))

    captured = capsys.readouterr()
    assert result.status == "event"
    assert captured.out == ""
    assert "enter completion configured_model=qwen/qwen3.5-9b" in captured.err
    assert "captured stdout from completion configured_model=qwen/qwen3.5-9b" in (
        captured.err
    )
    assert "completion configured_model=qwen/qwen3.5-9b" in captured.err
    assert "stdout> " in captured.err
    assert "Provider List: https://docs.litellm.ai/docs/providers" in captured.err


def test_openrouter_reports_text_interpretation_status() -> None:
    messages: list[str] = []

    OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        completion_func=lambda **kwargs: _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """
        ),
        cost_func=lambda **kwargs: 0.0,
    ).extract(
        InstagramPost(media_pk="1", shortcode="abc", caption="Live Set", media_kind="image"),
        status_callback=messages.append,
    )

    assert messages == ["Interpreting post text"]


def test_openrouter_encodes_local_cached_images_for_vision_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_bytes = b"fake image"
    image_path.write_bytes(image_bytes)
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _response(
                """
                {
                  "status": "needs_review",
                  "confidence": 0.2,
                  "events": [],
                  "warnings": []
                }
                """
            )
        return _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """
        )

    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        completion_func=completion,
        cost_func=lambda **kwargs: 0.0,
    ).extract(
        InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set May 3",
            media_kind="image",
            images=[ImageReference(uri=str(image_path))],
        )
    )

    assert result.status == "event"
    assert calls[1]["model"] == "openrouter/vision-model"
    image_url = calls[1]["messages"][1]["content"][1]["image_url"]["url"]
    assert image_url == f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"


def test_openrouter_reports_image_fallback_statuses(tmp_path: Path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_path.write_bytes(b"fake image")
    responses = iter(
        [
            _response(
                """
                {
                  "status": "needs_review",
                  "confidence": 0.2,
                  "events": [],
                  "warnings": []
                }
                """
            ),
            _response(
                """
                {
                  "status": "event",
                  "confidence": 0.91,
                  "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
                  "warnings": []
                }
                """
            ),
        ]
    )
    messages: list[str] = []

    OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        completion_func=lambda **kwargs: next(responses),
        cost_func=lambda **kwargs: 0.0,
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


def test_openrouter_encodes_local_cached_videos_for_final_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "poster.jpg"
    image_path.write_bytes(b"fake image")
    video_path = tmp_path / "clip.mp4"
    video_bytes = b"fake video"
    video_path.write_bytes(video_bytes)
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            return _response(
                """
                {
                  "status": "needs_review",
                  "confidence": 0.2,
                  "events": [],
                  "warnings": []
                }
                """
            )
        return _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """
        )

    messages: list[str] = []
    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        video_model="video-model",
        completion_func=completion,
        cost_func=lambda **kwargs: 0.0,
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
    assert calls[2]["model"] == "openrouter/video-model"
    video_url = calls[2]["messages"][1]["content"][1]["video_url"]["url"]
    assert video_url == f"data:video/mp4;base64,{base64.b64encode(video_bytes).decode()}"
    assert messages == [
        "Interpreting post text",
        "Falling back to image",
        "Interpreting image",
        "Falling back to video",
        "Interpreting video",
    ]


def test_openrouter_skips_remote_video_urls() -> None:
    calls = []
    messages: list[str] = []

    result = OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        video_model="video-model",
        completion_func=lambda **kwargs: calls.append(kwargs)
        or _response(
            """
            {
              "status": "needs_review",
              "confidence": 0.2,
              "events": [],
              "warnings": []
            }
            """
        ),
        cost_func=lambda **kwargs: 0.0,
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
    assert len(calls) == 1
    assert messages == [
        "Interpreting post text",
        "No image fallback available",
        "No video fallback available",
    ]


def test_openrouter_uses_vision_model_for_video_when_no_video_model(tmp_path: Path) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake video")
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _response(
                """
                {
                  "status": "needs_review",
                  "confidence": 0.2,
                  "events": [],
                  "warnings": []
                }
                """
            )
        return _response(
            """
            {
              "status": "event",
              "confidence": 0.91,
              "events": [{"title": "Live Set", "start": "2026-05-03T20:00:00-04:00"}],
              "warnings": []
            }
            """
        )

    OpenRouterExtractor(
        api_key="key",
        text_model="text-model",
        vision_model="vision-model",
        completion_func=completion,
        cost_func=lambda **kwargs: 0.0,
    ).extract(
        InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set",
            media_kind="video",
            videos=[VideoReference(uri=str(video_path))],
        )
    )

    assert calls[1]["model"] == "openrouter/vision-model"


def test_openrouter_validates_structured_model_output() -> None:
    with pytest.raises(ValueError, match="status"):
        OpenRouterExtractor(
            api_key="key",
            text_model="text-model",
            vision_model="vision-model",
            completion_func=lambda **kwargs: _response('{"status": "maybe", "events": []}'),
            cost_func=lambda **kwargs: 0.0,
        ).extract(InstagramPost(media_pk="1", caption="", media_kind="image"))
