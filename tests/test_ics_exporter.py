from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from instacalendar.exporters.ics import IcsExporter
from instacalendar.models import EventDraft


def test_ics_exporter_writes_uid_location_description_and_source(tmp_path: Path) -> None:
    draft = EventDraft(
        title="Live Set",
        description="Lineup: A, B",
        start=datetime(2026, 5, 3, 20, 0, tzinfo=ZoneInfo("America/New_York")),
        end=datetime(2026, 5, 3, 23, 0, tzinfo=ZoneInfo("America/New_York")),
        timezone="America/New_York",
        location_name="The Room",
        location_address="1 Main St",
        performers=["A", "B"],
        source_url="https://www.instagram.com/p/abc/",
        poster_profile_url="https://www.instagram.com/venue/",
    )

    output = tmp_path / "events.ics"
    records = IcsExporter().export(output, [("uid-1", draft)])

    text = output.read_text()
    assert records == [("uid-1", str(output))]
    assert "BEGIN:VEVENT" in text
    assert "UID:uid-1" in text
    assert "SUMMARY:Live Set" in text
    assert "LOCATION:The Room - 1 Main St" in text
    assert "https://www.instagram.com/p/abc/" in text
    assert "Posted by: https://www.instagram.com/venue/" in text
