# Instacalendar Initial App Implementation Plan

## Summary

Implement the PRD in [PRD-initial-features.md](PRD-initial-features.md) as a public, Windows-targeted Python CLI executable with a guided wizard. The app will read an authenticated Instagram saved collection, infer event data with OpenRouter text-first/vision-fallback extraction, require review before export, and write approved events to either `.ics` or Google Calendar.

Use Python 3.12 with `uv`, TDD-first development, and mocked external services in tests. Add README and architecture docs because the repo currently has no app architecture documentation.

## Key Changes

- Add runtime dependencies: `typer`, `questionary`, `rich`, `pydantic`, `platformdirs`, `keyring`, `instagrapi`, `httpx`, `google-api-python-client`, `google-auth-oauthlib`, `icalendar`, `pillow`, and `tzlocal`.
- Add dev/build dependencies: `pytest`, `pytest-mock`, `respx`, `ruff`, and `pyinstaller`.
- Replace the generated `instacalendar` entrypoint with a guided wizard: default `instacalendar` starts the full flow; `instacalendar auth`, `instacalendar run`, and `instacalendar cache` support setup, repeat runs, and troubleshooting.
- Store config under the user app config directory, cache/media under the user app data directory, and secrets in OS keyring where possible. Persist Instagram session settings to avoid repeated logins.
- Implement adapters for Instagram, OpenRouter, `.ics`, and Google Calendar behind small interfaces so tests use fakes and never call live services.

## Data Flow And Behavior

- Instagram: authenticate once through the wizard, support 2FA code prompts, persist session settings, list saved collections, and fetch all media from the selected collection. Use captions, post metadata, source URL, carousel images, and reel/video thumbnails; full video frame extraction is out of scope for v1.
- Extraction: call the configured text model first with caption/metadata and a strict JSON schema. If required fields are missing, confidence is low, or the model requests visual context, download/resize images and call the configured vision model with base64 image inputs.
- Model setup: fetch OpenRouter's Models API to validate/select models that support required modalities and structured outputs. Save user choices; allow manual model IDs if model discovery fails.
- Review: show each inferred event with source post, confidence, warnings, title, date/time, timezone, location, artists/lineup, and description. Require approve/edit/skip before any export.
- Cache: use SQLite to track posts, extraction attempts, review decisions, and exports. Idempotency keys are based on Instagram media PK plus event index/content hash plus destination.
- `.ics` export: write approved events to a user-chosen `.ics` file with stable UIDs, source URL, description, location, timezone-aware times, and all-day support.
- Google export: use desktop OAuth, list/select an existing calendar or create a secondary calendar, then insert approved events. Store a private extended property such as `instacalendar_uid` and query it before insert to prevent duplicates even if local cache is lost.

## Public Interfaces And Types

- CLI defaults:
  - `instacalendar`: launch guided wizard.
  - `instacalendar auth`: configure Instagram, OpenRouter, and Google credentials.
  - `instacalendar run`: run collection-to-calendar export with saved config and optional flags.
  - `instacalendar cache`: inspect or clear local processing records after confirmation.
- Core Pydantic contracts:
  - `InstagramPost`: media PK, shortcode/source URL, caption, taken-at timestamp, media kind, location metadata, image references.
  - `ExtractionResult`: `status` of `event`, `not_event`, or `needs_review`; list of event drafts; model IDs; confidence; warnings; raw response reference.
  - `EventDraft`: title, description, start, optional end, all-day flag, timezone, location name/address, performers, source URL, confidence, missing fields, evidence.
  - `ExportRecord`: stable UID, destination kind, destination ID/path, remote event ID when available, exported timestamp.
- Validation rule: title and start date/time are required before export. Missing location is allowed only after review confirmation and is recorded as a warning.

## Test Plan

- Start each behavior with failing tests, then implement the minimum code to pass.
- Unit tests:
  - config path resolution, keyring fallback behavior, and config serialization.
  - SQLite cache idempotency and state transitions.
  - Instagram adapter mapping using fake `instagrapi` media objects.
  - OpenRouter request payloads for text-only and image fallback, including JSON-schema validation and one retry on invalid JSON.
  - event validation for all-day, timezone-aware, missing-field, multi-event, and non-event cases.
  - `.ics` UID/date/location/description output.
  - Google duplicate detection and insert payloads using a fake Calendar service.
- CLI/wizard tests: use injected prompt adapters to test first-run setup, review approve/edit/skip, `.ics` export, and Google export choices without real terminal input.
- CI: run `uv run ruff check` and `uv run pytest` on Ubuntu; run a Windows packaging workflow with PyInstaller on `windows-latest` and upload the `.exe` artifact.
- Manual acceptance: run the executable on Windows, authenticate all three services, process a small test collection, approve at least one event, export to `.ics`, export to Google Calendar, rerun, and verify no duplicate export.

## Assumptions And External Requirements

- Public non-dev release requires the project owner to create and verify a Google OAuth desktop app before broad distribution. The build will inject the OAuth client JSON from a GitHub secret; local development can use an env var or local credentials file.
- Google scopes should be the narrow set needed for this PRD: list calendars, create secondary calendars, and create/update events. Avoid requesting full Calendar access unless testing shows it is required.
- `.ics` is the only calendar file format for v1 because it is the standard portable calendar format.
- OpenRouter receives event captions and images during extraction; README must disclose this clearly.
- Sources consulted: instagrapi collection/session docs, OpenRouter chat/images/structured-output/models docs, Google Calendar Python/OAuth/scopes/extended-properties docs, GitHub Actions Python docs, and PyInstaller docs.
