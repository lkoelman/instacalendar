from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import questionary
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeElapsedColumn
from rich.table import Table

from instacalendar.cache import EVENT_CACHE_KEYS, Cache
from instacalendar.config import AppPaths
from instacalendar.runner import AppRunner, ModelUsageTotal, RunSummary

app = typer.Typer(help="Turn Instagram saved event posts into calendar events.")
cache_app = typer.Typer(help="Inspect or clear local processing records.")
app.add_typer(cache_app, name="cache")
console = Console(width=180)


def _paths() -> AppPaths:
    return AppPaths.default()


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise typer.BadParameter("date must use YYYY-MM-DD format") from error


class QuestionaryPrompt:
    def text(self, message: str, *, default: str | None = None, password: bool = False) -> str:
        if password:
            question = questionary.password(message, default=default or "")
        else:
            question = questionary.text(message, default=default or "")
        answer = question.ask()
        if answer is None or answer == "":
            raise typer.Abort()
        return answer

    def choose(self, message: str, choices: list[str], *, default: str | None = None) -> str:
        answer = questionary.select(message, choices=choices, default=default).ask()
        if answer is None:
            raise typer.Abort()
        return answer

    def confirm(self, message: str, *, default: bool = True) -> bool:
        answer = questionary.confirm(message, default=default).ask()
        if answer is None:
            raise typer.Abort()
        return bool(answer)


class RichProgress:
    def status(self, message: str):
        return console.status(message, spinner="dots")

    def task(self, description: str, *, total: int):
        return RichProgressTask(description, total=total)


class RichProgressTask:
    def __init__(self, description: str, *, total: int) -> None:
        self.description = description
        self.total = total
        self.progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        )
        self.task_id: TaskID | None = None

    def __enter__(self) -> RichProgressTask:
        self.progress.start()
        self.task_id = self.progress.add_task(self.description, total=self.total)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.progress.stop()

    def update(self, message: str) -> None:
        if self.task_id is not None:
            self.progress.update(self.task_id, description=message)

    def advance(self) -> None:
        if self.task_id is not None:
            self.progress.advance(self.task_id)

    def report(self, message: str) -> None:
        self.progress.console.print(f"- {message}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    posted_since: Annotated[
        date | None,
        typer.Option(
            parser=_parse_date,
            help="Only process posts published on or after this date",
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum number of posts to process after filtering"),
    ] = None,
) -> None:
    if ctx.invoked_subcommand is None:
        console.print("Instacalendar guided wizard")
        runner = AppRunner(_paths(), QuestionaryPrompt(), progress=RichProgress())
        config = runner.configure()
        summary = runner.run(
            destination=config.default_export,
            posted_since=posted_since,
            limit=limit,
        )
        console.print(
            f"Exported {summary.exported_events} events from {summary.processed_posts} posts "
            f"to {summary.destination}"
        )
        _print_extraction_cost_summary(summary)


@app.command()
def init(
    instagram_username: Annotated[str | None, typer.Option()] = None,
    instagram_password: Annotated[str | None, typer.Option()] = None,
    openrouter_api_key: Annotated[str | None, typer.Option()] = None,
    openrouter_text_model: Annotated[str | None, typer.Option()] = None,
    openrouter_vision_model: Annotated[str | None, typer.Option()] = None,
    openrouter_video_model: Annotated[str | None, typer.Option()] = None,
    default_export: Annotated[str, typer.Option()] = "ics",
    google_calendar_id: Annotated[str | None, typer.Option()] = None,
    authenticate_google: Annotated[
        bool | None,
        typer.Option(
            "--google-auth/--no-google-auth",
            help="Run or skip Google Calendar browser authentication during setup",
        ),
    ] = None,
) -> None:
    if default_export not in {"ics", "google"}:
        raise typer.BadParameter("default export must be 'ics' or 'google'")
    AppRunner(_paths(), QuestionaryPrompt(), progress=RichProgress()).configure(
        instagram_username=instagram_username,
        instagram_password=instagram_password,
        openrouter_api_key=openrouter_api_key,
        openrouter_text_model=openrouter_text_model,
        openrouter_vision_model=openrouter_vision_model,
        openrouter_video_model=openrouter_video_model,
        default_export=default_export,
        google_calendar_id=google_calendar_id,
        authenticate_google=authenticate_google,
    )
    console.print(f"Saved configuration to {_paths().config_file}")


@app.command()
def run(
    collection: Annotated[str | None, typer.Option(help="Instagram saved collection name")] = None,
    ics_output: Annotated[
        Path | None, typer.Option(help="Path for .ics export when using file export")
    ] = None,
    posted_since: Annotated[
        date | None,
        typer.Option(
            parser=_parse_date,
            help="Only process posts published on or after this date",
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum number of posts to process after filtering"),
    ] = None,
    from_cache: Annotated[
        bool,
        typer.Option("--from-cache", help="Use cached posts instead of fetching Instagram"),
    ] = False,
    ignore_event_cache: Annotated[
        bool,
        typer.Option(
            "--ignore-event-cache",
            help="Reprocess posts instead of reusing cached extraction results",
        ),
    ] = False,
    event_cache_key: Annotated[
        str,
        typer.Option(
            "--event-cache-key",
            help="Cache hit policy: post, post,media, model, or model,media",
        ),
    ] = "model,media",
) -> None:
    if event_cache_key not in EVENT_CACHE_KEYS:
        raise typer.BadParameter(
            "event cache key must be one of: post, post,media, model, model,media"
        )
    summary = AppRunner(_paths(), QuestionaryPrompt(), progress=RichProgress()).run(
        collection=collection,
        ics_output=ics_output,
        posted_since=posted_since,
        limit=limit,
        from_cache=from_cache,
        ignore_event_cache=ignore_event_cache,
        event_cache_key=event_cache_key,
    )
    console.print(
        f"Exported {summary.exported_events} events from {summary.processed_posts} posts "
        f"to {summary.destination}"
    )
    _print_extraction_cost_summary(summary)


@cache_app.command("calendar", help="Show previously exported calendar events")
def cache_calendar() -> None:
    cache = Cache(_paths().cache_file)
    cache.initialize()
    exports = cache.list_exports()
    if not exports:
        console.print("No exports recorded")
        return
    for export in exports:
        console.print(
            f"{export.exported_at} {export.destination_kind} {export.destination_id} {export.uid}"
        )


@cache_app.command("events", help="Show cached event extraction results")
def cache_events() -> None:
    cache = Cache(_paths().cache_file)
    cache.initialize()
    extractions = cache.list_cached_extractions()
    if not extractions:
        console.print("No extracted events recorded")
        return
    table = Table()
    table.add_column("Media PK")
    table.add_column("Model")
    table.add_column("Media Kind")
    table.add_column("Extracted At")
    table.add_column("Status")
    table.add_column("Events")
    table.add_column("Warnings", justify="right")
    for ex in extractions:
        events_text = ", ".join(ex.event_titles)
        if len(events_text) > 40:
            events_text = events_text[:37] + "..."
        table.add_row(
            ex.media_pk,
            ex.model_signature,
            ex.source_media_kind,
            ex.extracted_at,
            ex.status,
            events_text,
            str(ex.warnings_count),
        )
    console.print(table)


@cache_app.command("list-posts", help="Show cached Instagram posts and media status")
def cache_list_posts(
    collection: Annotated[
        str | None, typer.Option(help="Only show cached posts from this collection")
    ] = None,
) -> None:
    cache = Cache(_paths().cache_file)
    cache.initialize()
    posts = cache.list_cached_posts(collection)
    if not posts:
        console.print("No cached posts recorded")
        return
    table = Table()
    table.add_column("Fetched")
    table.add_column("Collection")
    table.add_column("Posted")
    table.add_column("Media PK")
    table.add_column("Shortcode")
    table.add_column("Kind")
    table.add_column("Images", justify="right")
    table.add_column("Videos", justify="right")
    table.add_column("Missing", justify="right")
    table.add_column("Caption")
    for post in posts:
        table.add_row(
            post.fetched_at,
            post.collection_name,
            post.taken_at or "",
            post.media_pk,
            post.shortcode or "",
            post.media_kind,
            str(post.cached_images),
            str(post.cached_videos),
            str(post.missing_media),
            post.caption_preview,
        )
    console.print(table)


@cache_app.command("info", help="Show cache size and collection breakdown")
def cache_info() -> None:
    paths = _paths()
    cache = Cache(paths.cache_file)
    cache.initialize()
    info = cache.cache_info(paths.media_dir)
    console.print(f"Cache file: {info.cache_file}")
    console.print(f"Media directory: {info.media_dir}")
    console.print(f"Database storage: {_format_bytes(info.database_size_bytes)}")
    console.print(f"Media storage: {_format_bytes(info.media_size_bytes)}")
    console.print(f"Total storage: {_format_bytes(info.total_size_bytes)}")
    console.print(f"Total files: {_format_file_counts(info.total_file_counts)}")
    if info.missing_media_count:
        console.print(f"Missing media records: {info.missing_media_count}")

    if not info.collections:
        console.print("No cached media recorded")
        return

    table = Table(title="Cache By Collection")
    table.add_column("Collection")
    table.add_column("Images", justify="right")
    table.add_column("Videos", justify="right")
    table.add_column("Other", justify="right")
    table.add_column("Missing", justify="right")
    table.add_column("Storage", justify="right")
    for collection in info.collections:
        table.add_row(
            collection.collection_name,
            str(collection.file_counts.get("image", 0)),
            str(collection.file_counts.get("video", 0)),
            str(
                sum(
                    count
                    for kind, count in collection.file_counts.items()
                    if kind not in {"image", "video"}
                )
            ),
            str(collection.missing_media_count),
            _format_bytes(collection.size_bytes),
        )
    console.print(table)


@cache_app.command("clear", help="Delete all cached data and media files")
def cache_clear(
    yes: Annotated[bool, typer.Option("--yes", help="Confirm cache deletion")] = False,
) -> None:
    path = _paths().cache_file
    if not yes:
        raise typer.Abort()
    if path.exists():
        path.unlink()
    if _paths().media_dir.exists():
        shutil.rmtree(_paths().media_dir)
    Cache(path).initialize()
    console.print(f"Cleared cache at {datetime.now(UTC).isoformat()}")


def _format_file_counts(file_counts: dict[str, int]) -> str:
    if not file_counts:
        return "0 files"
    parts = [f"{kind}: {file_counts[kind]}" for kind in sorted(file_counts)]
    return ", ".join(parts)


def _print_extraction_cost_summary(summary: RunSummary) -> None:
    if not summary.extraction_usage_by_model:
        return
    total_cost = _total_cost(summary.extraction_usage_by_model)
    console.print(f"Extraction cost: est. {_format_cost(total_cost)}")
    for model, usage in sorted(summary.extraction_usage_by_model.items()):
        console.print(
            f"- {model}: {usage.total_tokens} tokens "
            f"({_format_cost(usage.estimated_cost_usd)}, {usage.calls} calls)"
        )


def _total_cost(usage_by_model: dict[str, ModelUsageTotal]) -> float | None:
    total = 0.0
    for usage in usage_by_model.values():
        if usage.estimated_cost_usd is None:
            return None
        total += usage.estimated_cost_usd
    return total


def _format_cost(cost: float | None) -> str:
    if cost is None:
        return "unavailable"
    return f"${cost:.4f}"


def _format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
