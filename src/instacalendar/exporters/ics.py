from __future__ import annotations

from pathlib import Path

from icalendar import Calendar, Event, vCalAddress, vText

from instacalendar.models import EventDraft


class IcsExporter:
    def export(
        self, output_path: Path, events: list[tuple[str, EventDraft]]
    ) -> list[tuple[str, str]]:
        calendar = Calendar()
        calendar.add("prodid", "-//instacalendar//Instagram saved posts to calendar//EN")
        calendar.add("version", "2.0")

        for uid, draft in events:
            event = Event()
            event.add("uid", uid)
            event.add("summary", draft.title)
            if draft.start is not None:
                event.add("dtstart", draft.start.date() if draft.all_day else draft.start)
            if draft.end is not None:
                event.add("dtend", draft.end.date() if draft.all_day else draft.end)
            location = draft.display_location()
            if location:
                event.add("location", vText(location))
            description = draft.description
            if draft.performers:
                description = f"{description}\n\nPerformers: {', '.join(draft.performers)}".strip()
            if draft.source_url:
                description = f"{description}\n\nSource: {draft.source_url}".strip()
                event.add("url", vCalAddress(draft.source_url))
            if draft.poster_profile_url:
                description = f"{description}\n\nPosted by: {draft.poster_profile_url}".strip()
            if description:
                event.add("description", description)
            calendar.add_component(event)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(calendar.to_ical())
        return [(uid, str(output_path)) for uid, _ in events]
