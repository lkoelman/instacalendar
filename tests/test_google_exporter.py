from datetime import datetime
from zoneinfo import ZoneInfo

from instacalendar.exporters.google import GoogleCalendarExporter
from instacalendar.models import EventDraft


def test_google_exporter_builds_duplicate_safe_event_body() -> None:
    draft = EventDraft(
        title="Live Set",
        description="Lineup announced",
        start=datetime(2026, 5, 3, 20, 0, tzinfo=ZoneInfo("America/New_York")),
        timezone="America/New_York",
        location_name="The Room",
        source_url="https://www.instagram.com/p/abc/",
    )

    body = GoogleCalendarExporter(service=None).build_event_body("uid-1", draft)

    assert body["summary"] == "Live Set"
    assert body["start"]["dateTime"] == "2026-05-03T20:00:00-04:00"
    assert body["start"]["timeZone"] == "America/New_York"
    assert body["location"] == "The Room"
    assert body["extendedProperties"]["private"]["instacalendar_uid"] == "uid-1"
    assert "Source: https://www.instagram.com/p/abc/" in body["description"]
