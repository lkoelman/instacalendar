# Architecture

## Overview

`instacalendar` is split into a small CLI shell, testable orchestration code,
and adapters for each external system.

- `instacalendar.cli` owns Typer commands and Questionary prompts.
- `instacalendar.runner` coordinates configuration, authentication, collection
  fetching, extraction, review, export, and cache writes.
- `instacalendar.models` defines Pydantic contracts shared across adapters.
- `instacalendar.config` and `instacalendar.secrets` handle app paths,
  serialized config, keyring secrets, and local fallback storage.
- `instacalendar.cache` stores review/export idempotency state in SQLite.
- `instacalendar.instagram` maps `instagrapi` media objects to normalized posts
  and persists session settings.
- `instacalendar.extractors.openrouter` performs text-first extraction and
  vision fallback when image references are available.
- `instacalendar.exporters.ics` writes portable calendar files.
- `instacalendar.exporters.google` builds Google Calendar events and avoids
  duplicates with a private `instacalendar_uid` extended property.
- `instacalendar.google_auth` runs the desktop OAuth flow and stores refreshable
  credentials in the app data directory.

## Data Flow

1. CLI loads config and secrets or asks the user for missing setup values.
2. Instagram login reuses a saved session file when possible.
3. The selected saved collection is fetched and mapped to `InstagramPost`.
4. OpenRouter receives caption and metadata through the configured text model.
5. If confidence is low or the result needs review and images exist, the vision
   model receives the same metadata plus image references.
6. Candidate `EventDraft` objects are shown to the user for approval or skip.
7. Approved events are exported to `.ics` or Google Calendar.
8. SQLite records review and export state using stable UIDs to prevent reruns
   from exporting the same event to the same destination.

## Testing Strategy

Tests mock external services and exercise adapter boundaries:

- model validation and required export fields,
- config serialization and app path overrides,
- SQLite idempotency,
- Instagram media mapping,
- OpenRouter request payloads and JSON parsing,
- ICS output content,
- Google duplicate-safe event payloads,
- CLI setup and cache commands.
