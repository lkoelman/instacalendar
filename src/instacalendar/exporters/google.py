from __future__ import annotations

from datetime import date, datetime
from typing import Any

from instacalendar.models import EventDraft


class GoogleCalendarExporter:
    def __init__(self, service: Any) -> None:
        self.service = service

    def build_event_body(self, uid: str, draft: EventDraft) -> dict[str, Any]:
        body: dict[str, Any] = {
            "summary": draft.title,
            "description": self._description(draft),
            "location": draft.display_location() or None,
            "extendedProperties": {"private": {"instacalendar_uid": uid}},
        }
        if draft.all_day:
            body["start"] = {"date": self._date_value(draft.start)}
            body["end"] = {"date": self._date_value(draft.end or draft.start)}
        else:
            body["start"] = {
                "dateTime": self._datetime_value(draft.start),
                "timeZone": draft.timezone,
            }
            if draft.end:
                body["end"] = {
                    "dateTime": self._datetime_value(draft.end),
                    "timeZone": draft.timezone,
                }
        return {key: value for key, value in body.items() if value is not None}

    def insert_if_missing(self, calendar_id: str, uid: str, draft: EventDraft) -> str:
        existing = (
            self.service.events()
            .list(
                calendarId=calendar_id,
                privateExtendedProperty=f"instacalendar_uid={uid}",
                maxResults=1,
                singleEvents=True,
            )
            .execute()
        )
        items = existing.get("items", [])
        if items:
            return items[0]["id"]
        created = (
            self.service.events()
            .insert(calendarId=calendar_id, body=self.build_event_body(uid, draft))
            .execute()
        )
        return created["id"]

    def _description(self, draft: EventDraft) -> str:
        parts = [draft.description]
        if draft.performers:
            parts.append(f"Performers: {', '.join(draft.performers)}")
        if draft.source_url:
            parts.append(f"Source: {draft.source_url}")
        if draft.poster_profile_url:
            parts.append(f"Posted by: {draft.poster_profile_url}")
        return "\n\n".join(part for part in parts if part)

    def _datetime_value(self, value: datetime | None) -> str:
        if value is None:
            raise ValueError("timed events require a datetime")
        return value.isoformat()

    def _date_value(self, value: datetime | date | None) -> str:
        if value is None:
            raise ValueError("all-day events require a date")
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
