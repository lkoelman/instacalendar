<p align="center">
  <img src="docs/assets/instacalendar_logo_640x640.jpg" alt="InstaCalendar logo" width="320" />
</p>

<h1 align="center">Instacalendar</h1>

<p align="center">
  <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/lkoelman/instacalendar">
  <img alt="GitHub forks" src="https://img.shields.io/github/forks/lkoelman/instacalendar">
  <img alt="GitHub Issues or Pull Requests" src="https://img.shields.io/github/issues/lkoelman/instacalendar">
  <a href="https://github.com/lkoelman/instacalendar/actions"><img alt="CI Status" src="https://github.com/lkoelman/instacalendar/actions/workflows/ci.yml/badge.svg" /></a>
  <img alt="PyPI package version" src="https://img.shields.io/pypi/v/instacalendar" />
</p>

> Scenario: you're like me and save lots of gigs and events in Instagram. Then you forget about them. Life's busy and it's hard to keep track of all those fun events without aligning them with your boring, grown-up calendar. Meet Instacalendar: seamlessly sync an entire Instragram saved post collection to your Google (or other) calendar. Keep track of those events, plan better, go out and explore!

`instacalendar` is a command-line wizard that reads an Instagram saved posts
collection, asks OpenRouter models through LiteLLM to infer calendar events,
lets you review each candidate event, and exports approved events to `.ics` or
Google Calendar.

The app can be installed as a Python package or as a Windows executable bundled with PyInstaller.

## TLDR

```bash
# install
uv tool install instacalendar
# OR: `pip install instacalendar`

# run setup
instacalendar init

# run interactively (fetch Instagram collections and select one)
instacalendar

# export specific collection
instacalendar run --collection "Concerts" --ics-output events.ics
```

## Installation

### Install From PyPI

See TLDR section.

### Install From Source

```bash
git clone https://github.com/lkoelman/instacalendar.git
cd instacalendar
uv sync --dev
```

Because `instagrapi` tracks the undocumented Instagram API at a fast-changing pace, upgrading this dependency regularly could prevent bugs arising due to API divergence:

```bash
# upgrade out environment and uv.lock file:
uv sync --upgrade-package instagrapi

# upgrade instagrapi before running a command
uv run --upgrade-package instagrapi instacalendar <command>
```

## Configure

Run the guided setup:

```bash
uv run instacalendar init
```

Or provide values non-interactively:

```bash
uv run instacalendar init \
  --instagram-username your_user \
  --instagram-password your_password \
  --openrouter-api-key sk-or-v1-... \
  --openrouter-text-model google/gemini-3-flash-preview \
  --openrouter-vision-model google/gemini-3-flash-preview \
  --openrouter-video-model google/gemini-3-flash-preview \
  --default-export ics
```

If `OPENROUTER_API_KEY` or `INSTAGRAM_PASSWORD` is set in your environment, setup asks whether to use
that value before prompting you to type one.

Secrets are stored in the operating system keyring. Instagram session settings are stored
under the app data directory to avoid repeated logins.

### Google Calendar Export

For now, just import the .ics file in your Google Calendar. In the future, an OAuth Client ID will be created so you can directly push events to your Google calendar.

For Google Calendar export, authenticate during setup:

```bash
uv run instacalendar init --default-export google --google-auth
```

The command opens a Google consent link in your browser and stores the resulting
OAuth token under the app data directory. Later Google Calendar exports reuse
and refresh that token when possible.

Release builds can ship an Instacalendar desktop OAuth client so normal users do
not need to create Google Cloud credentials. For development, private forks, or
builds without a bundled OAuth client, set one of these environment variables
before running `--google-auth`:

```bash
export GOOGLE_OAUTH_CLIENT_FILE=/path/to/oauth-client.json
# or
export GOOGLE_OAUTH_CLIENT_JSON='{"installed": ... }'
```

The OAuth client must be a Google desktop app. The app requests the
`calendar.events` scope needed to read and write calendar events.

## Run

Start the guided wizard:

```bash
uv run instacalendar
```

Export a collection directly:

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
uv run instacalendar cache calendar
uv run instacalendar cache events
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
