# instacalendar

> Scenario: you're like me and save lots of gigs, events in Instagram and then forget about them. You're a busy person so it's hard to keep track of all those fun events without aligning them with your boring, grown-up calendar. Meet InstaCalendar: seamlessly sync an entire Instragram saved post collection to your Google (or other) calendar. Keep track of those events, plan better, go out and explore!

`instacalendar` is a command-line wizard that reads an Instagram saved posts
collection, asks OpenRouter models to infer calendar events, lets you review
each candidate event, and exports approved events to `.ics` or Google Calendar.

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
  --default-export ics
```

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

Inspect processed exports:

```bash
uv run instacalendar cache list
```

Clear the local cache:

```bash
uv run instacalendar cache clear --yes
```

## Privacy

Instagram captions, post metadata, and image URLs for posts being processed are
sent to OpenRouter for extraction. Google Calendar export sends approved event
details to Google. The local SQLite cache stores post IDs, review decisions, and
export records so reruns do not create duplicates.

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
