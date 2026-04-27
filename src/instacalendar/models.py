from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImageReference(BaseModel):
    """Local or remote image attached to an Instagram post."""

    uri: str
    mime_type: str | None = None


class VideoReference(BaseModel):
    """Local or remote video attached to an Instagram post."""

    uri: str
    mime_type: str | None = None


class InstagramPost(BaseModel):
    """Normalized Instagram media used by extraction adapters."""

    media_pk: str
    poster_username: str | None = None
    shortcode: str | None = None
    caption: str = ""
    taken_at: datetime | None = None
    media_kind: str
    location_name: str | None = None
    location_address: str | None = None
    images: list[ImageReference] = Field(default_factory=list)
    videos: list[VideoReference] = Field(default_factory=list)

    @property
    def source_url(self) -> str | None:
        if not self.shortcode:
            return None
        return f"https://www.instagram.com/p/{self.shortcode}/"

    @property
    def poster_profile_url(self) -> str | None:
        if not self.poster_username:
            return None
        username = self.poster_username.removeprefix("@").strip("/")
        if not username:
            return None
        return f"https://www.instagram.com/{username}/"


class EventDraft(BaseModel):
    """Candidate calendar event inferred from an Instagram post."""

    title: str
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    timezone: str | None = None
    location_name: str | None = None
    location_address: str | None = None
    description: str = ""
    performers: list[str] = Field(default_factory=list)
    source_url: str | None = None
    poster_profile_url: str | None = None
    confidence: float | None = None
    missing_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("confidence")
    @classmethod
    def _confidence_between_zero_and_one(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def _end_not_before_start(self) -> EventDraft:
        if self.start and self.end and self.end < self.start:
            raise ValueError("end must not be before start")
        return self

    @property
    def is_exportable(self) -> bool:
        return not self.missing_required_fields()

    def missing_required_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.title.strip():
            missing.append("title")
        if self.start is None:
            missing.append("start")
        return missing

    def display_location(self) -> str:
        if self.location_name and self.location_address:
            return f"{self.location_name} - {self.location_address}"
        return self.location_name or self.location_address or ""


class ExtractionResult(BaseModel):
    """Structured model output for one Instagram post."""

    status: Literal["event", "not_event", "needs_review"]
    events: list[EventDraft] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)
    raw_response_ref: str | None = None

    @model_validator(mode="after")
    def _event_status_has_events(self) -> ExtractionResult:
        if self.status == "event" and not self.events:
            raise ValueError("event results require at least one event draft")
        return self


class ExportRecord(BaseModel):
    uid: str
    destination_kind: Literal["ics", "google"]
    destination_id: str
    remote_event_id: str | None = None
    exported_at: datetime
