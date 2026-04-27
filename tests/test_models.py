from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from instacalendar.models import EventDraft, ExtractionResult, InstagramPost


def test_event_draft_requires_title_and_start_for_export() -> None:
    draft = EventDraft(
        title="",
        start=datetime(2026, 5, 3, 20, 0, tzinfo=ZoneInfo("America/New_York")),
        timezone="America/New_York",
        source_url="https://instagram.com/p/example",
    )

    assert draft.missing_required_fields() == ["title"]
    assert not draft.is_exportable


def test_event_draft_all_day_accepts_date_only_midnight() -> None:
    draft = EventDraft(
        title="Festival",
        start=datetime(2026, 5, 3, 0, 0, tzinfo=ZoneInfo("Europe/Paris")),
        all_day=True,
        timezone="Europe/Paris",
        source_url="https://instagram.com/p/example",
    )

    assert draft.is_exportable
    assert draft.missing_required_fields() == []


def test_extraction_result_event_requires_at_least_one_draft() -> None:
    with pytest.raises(ValueError, match="event results require"):
        ExtractionResult(status="event", events=[], model_ids=["openai/gpt"])


def test_instagram_post_source_url_from_shortcode() -> None:
    post = InstagramPost(
        media_pk="123",
        poster_username="venue",
        shortcode="abcDEF",
        caption="May 3 at The Room",
        taken_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
        media_kind="image",
    )

    assert post.source_url == "https://www.instagram.com/p/abcDEF/"
    assert post.poster_profile_url == "https://www.instagram.com/venue/"
