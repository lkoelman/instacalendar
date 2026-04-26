<p align="center">
  <img src="docs/assets/instacalendar_logo_640x640.jpg" alt="InstaCalendar logo" width="320" />
</p>

<h1 align="center">Instacalendar</h1>


> Scenario: you're like me and save lots of gigs and events in Instagram. Then you forget about them. Life's busy and it's hard to keep track of all those fun events without aligning them with your boring, grown-up calendar. Meet Instacalendar: seamlessly sync an entire Instragram saved post collection to your Google (or other) calendar. Keep track of those events, plan better, go out and explore!

`instacalendar` is a command-line wizard that reads an Instagram saved posts
collection, asks OpenRouter models through LiteLLM to infer calendar events,
lets you review each candidate event, and exports approved events to `.ics` or
Google Calendar.

The app can be installed as Python package or as a Windows executable bundled with PyInstaller.

## Install For Development

```bash
uv sync --dev
```

## Configure

Run the guided setup:

```bash
uv run instacalendar auth
```

Or provide values non-interactively:

```bash
uv run instacalendar auth \
  --instagram-username your_user \
  --instagram-password your_password \
  --openrouter-api-key sk-or-v1-... \
  --openrouter-text-model openai/gpt-4o-mini \
  --openrouter-vision-model openai/gpt-4o \
  --openrouter-video-model google/gemini-2.5-flash \
  --default-export ics
```

If `OPENROUTER_API_KEY` is set in your environment, setup asks whether to use
that key before prompting you to type one.

Secrets are stored in the operating system keyring when available, with a local
fallback under the app config directory. Instagram session settings are stored
under the app data directory to avoid repeated logins.

For Google Calendar export, set one of these environment variables before
running:

```bash
export GOOGLE_OAUTH_CLIENT_FILE=/path/to/oauth-client.json
# or
export GOOGLE_OAUTH_CLIENT_JSON='{"installed": ... }'
```

The OAuth client must be a Google desktop app. The app requests Calendar scopes
needed to list calendars and insert events.

## Run

Start the guided wizard:

```bash
uv run instacalendar
```

Run a configured collection directly:

```bash
uv run instacalendar run --collection "Concerts" --ics-output events.ics
```

Extracted event results are cached locally as each post is processed, so a
failed or interrupted run can resume without sending already processed posts
back to OpenRouter when the configured model set still matches. To force a fresh
extraction pass, use:

```bash
uv run instacalendar run --collection "Concerts" --ignore-event-cache
```

By default, cache hits require the same post, same configured OpenRouter model
set, and same extraction source type (`text`, `image`, or `video`). You can
relax matching when needed:

```bash
uv run instacalendar run --collection "Concerts" --event-cache-key post,media
```

Retry extraction/export from posts already saved in the local cache:

```bash
uv run instacalendar run --from-cache --collection "Concerts" --ics-output events.ics
```

Limit processing to recent posts, or cap how many matching posts are reviewed:

```bash
uv run instacalendar run --collection "Concerts" --posted-since 2026-04-01 --limit 25
```

While extraction is running, the progress output shows runtime-only estimated
LLM cost and token usage for each post and for the run so far, grouped by model.
The final summary prints the same per-model token and estimated cost totals.
These estimates come from LiteLLM/OpenRouter response usage metadata and are not
persisted in the local cache.

Inspect cached posts and processed exports:

```bash
uv run instacalendar cache list-posts
uv run instacalendar cache list-events
uv run instacalendar cache info
```

Clear the local cache:

```bash
uv run instacalendar cache clear --yes
```

## Privacy

Instagram captions, post metadata, image content, and cached local video content
for posts being processed may be sent to OpenRouter for extraction. Remote
Instagram video URLs are not sent when the local video download failed. Google
Calendar export sends approved event details to Google. The local cache stores
post metadata, downloaded image and video files, extracted event results, review
decisions, and export records so reruns can resume extraction/export without
contacting Instagram unnecessarily, avoid repeated OpenRouter calls for matching
posts, and avoid duplicate exports. Model responses are validated against the
app's Pydantic extraction schema before they are cached or reviewed.

## Test And Lint

```bash
uv run pytest
uv run ruff check
```

## Build A Windows Executable

On Windows:

```powershell
uv sync --dev
uv run pyinstaller --onefile --name instacalendar src/instacalendar/cli.py
```
