# Post Content Caching Implementation Plan

## Summary

Revamp the cache so it stores fetched Instagram posts and their local media files, not only review/export records. A live Instagram run should cache the posts selected for processing after `--posted-since` and `--limit`, download image and video media best-effort, and continue through extraction/export as it does today.

Add `instacalendar run --from-cache` so a user can retry extraction and export from already fetched posts without contacting Instagram. This is intended for retries with a different OpenRouter model, changed prompt behavior, or interrupted export work. Existing duplicate-export protection remains in place: reprocessing cached posts should not force duplicate exports when the same generated UID has already been exported to the same destination.

## Key Changes

- Extend the post/media data model so `InstagramPost` can represent cached videos as well as existing image references.
- Add SQLite storage for cached post metadata and cached media metadata, preserving the current `reviews` and `exports` tables.
- Store media files under `AppPaths.media_dir`, using deterministic paths such as `data/media/<collection-slug>/<media_pk>/image-0.jpg` and `video-0.mp4`.
- Cache rows should include collection name, media PK, post JSON, fetch timestamp, media source URLs, local file paths, media kind, download status, and any media download error.
- Update the Instagram adapter to collect top-level and carousel image URLs plus video URLs from `media.video_url` and `resource.video_url`.
- Add cache APIs to store processed posts, list cached collections, load cached posts for extraction, and list cached post summaries.
- Update OpenRouter image handling so cached local image files are encoded as data URLs for vision-model calls; cached videos are stored and listed but are not sent to OpenRouter in this change.
- Add `instacalendar run --from-cache`:
  - if `--collection` is provided, load that cached collection;
  - otherwise prompt from cached collection names;
  - bypass Instagram config/password lookup, authentication, collection listing, and fetch;
  - still require OpenRouter config/API key and normal export configuration.
- Rename `instacalendar cache list` to `instacalendar cache list-events`; do not keep a `cache list` compatibility alias.
- Add `instacalendar cache list-posts [--collection NAME]` with a clear Rich table showing fetched time, collection, posted time, media PK, shortcode, media kind, cached image/video counts, missing media count, and caption preview.
- Update `cache clear --yes` to clear both the SQLite cache file and cached media directory, then reinitialize the database.
- Update README and ARCHITECTURE to document `--from-cache`, `cache list-events`, `cache list-posts`, media caching, and the fact that videos are cached but not extracted.

## Data Flow And Behavior

- Live run:
  - initialize cache and load config/secrets;
  - authenticate with Instagram and fetch the selected collection;
  - apply `--posted-since` and `--limit`;
  - cache only the posts selected for processing;
  - download image and video media into the media cache;
  - keep posts even when one or more media downloads fail, recording the failed media status;
  - run extraction/export using the cached local media references where available.
- Cached run:
  - initialize cache and load config/secrets needed for extraction/export;
  - resolve the cached collection from `--collection` or by prompting from cached collection names;
  - load cached posts and apply existing `--posted-since` and `--limit` filters to cached metadata;
  - run extraction/export without instantiating `LiveInstagramClient`;
  - record reviews and exports exactly like a live run.
- Empty cache behavior:
  - `run --from-cache` should fail clearly if there are no cached collections;
  - `run --from-cache --collection NAME` should fail clearly if that collection has no cached posts.

## Public Interfaces And Types

- CLI:
  - add `instacalendar run --from-cache`;
  - rename `instacalendar cache list` to `instacalendar cache list-events`;
  - add `instacalendar cache list-posts [--collection NAME]`.
- Cache API:
  - add methods for upserting cached posts and media records;
  - add methods for listing cached collections and post summaries;
  - add a method for loading cached posts back into `InstagramPost` objects.
- Models:
  - keep current `ImageReference` behavior for extractor compatibility;
  - add a video media representation or generalized media reference only as needed to distinguish cached image and video files without disrupting existing image extraction.

## Test Plan

- Start with failing tests for each new behavior.
- Cache tests:
  - tables are created idempotently;
  - cached posts and media upsert by collection/media PK;
  - cached posts round-trip back to `InstagramPost`;
  - failed media downloads are recorded without dropping the post;
  - cached post summaries report image/video/missing counts.
- Runner tests:
  - live runs cache only filtered/limited posts;
  - `--from-cache` bypasses Instagram entirely;
  - cached collection prompting works when `--collection` is omitted;
  - missing or empty cached collections fail clearly;
  - export idempotency still skips already exported UIDs.
- CLI tests:
  - `run --from-cache` passes the flag into `AppRunner.run`;
  - `cache list-events` replaces `cache list`;
  - `cache list-posts` renders multi-column output;
  - `cache clear --yes` deletes cached media as well as the SQLite cache.
- Instagram adapter tests:
  - top-level image and video references are mapped;
  - carousel image and video resources are mapped.
- OpenRouter tests:
  - local cached image files are encoded as data URLs;
  - remote image URLs still pass through unchanged.
- Documentation checks:
  - README examples use `cache list-events` and document `run --from-cache`;
  - ARCHITECTURE reflects post/media cache responsibilities.
- Run `uv run pytest` and `uv run ruff check`.

## Assumptions And External Requirements

- `--from-cache` is implemented on `instacalendar run`, not on the root guided wizard.
- Live runs cache only posts that will be processed after filters and limits.
- Media download failures are non-fatal: cache the post, cache successful media, record failed media, and continue.
- Cached videos are for local completeness and future extraction work; this change does not add video analysis.
- Re-export means re-running extraction/export from cached posts, not bypassing existing duplicate-export safeguards.
- The existing untracked bug spec files are unrelated to this plan and should not be modified by this work.
