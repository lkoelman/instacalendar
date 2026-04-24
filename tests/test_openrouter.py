import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import respx

from instacalendar.extractors.openrouter import OpenRouterExtractor
from instacalendar.models import InstagramPost


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
