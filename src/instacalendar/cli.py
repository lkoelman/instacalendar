from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import questionary
import typer
from rich.console import Console

from instacalendar.cache import Cache
from instacalendar.config import AppPaths
from instacalendar.runner import AppRunner

app = typer.Typer(help="Turn Instagram saved event posts into calendar events.")
cache_app = typer.Typer(help="Inspect or clear local processing records.")
app.add_typer(cache_app, name="cache")
console = Console()


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


@app.command()
def auth(
    instagram_username: Annotated[str | None, typer.Option()] = None,
    instagram_password: Annotated[str | None, typer.Option()] = None,
    openrouter_api_key: Annotated[str | None, typer.Option()] = None,
    openrouter_text_model: Annotated[str | None, typer.Option()] = None,
    openrouter_vision_model: Annotated[str | None, typer.Option()] = None,
    default_export: Annotated[str, typer.Option()] = "ics",
    google_calendar_id: Annotated[str | None, typer.Option()] = None,
) -> None:
    if default_export not in {"ics", "google"}:
        raise typer.BadParameter("default export must be 'ics' or 'google'")
    AppRunner(_paths(), QuestionaryPrompt(), progress=RichProgress()).configure(
        instagram_username=instagram_username,
        instagram_password=instagram_password,
        openrouter_api_key=openrouter_api_key,
        openrouter_text_model=openrouter_text_model,
        openrouter_vision_model=openrouter_vision_model,
        default_export=default_export,
        google_calendar_id=google_calendar_id,
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
) -> None:
    summary = AppRunner(_paths(), QuestionaryPrompt(), progress=RichProgress()).run(
        collection=collection,
        ics_output=ics_output,
        posted_since=posted_since,
        limit=limit,
    )
    console.print(
        f"Exported {summary.exported_events} events from {summary.processed_posts} posts "
        f"to {summary.destination}"
    )


@cache_app.command("list")
def cache_list() -> None:
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


@cache_app.command("clear")
def cache_clear(
    yes: Annotated[bool, typer.Option("--yes", help="Confirm cache deletion")] = False,
) -> None:
    path = _paths().cache_file
    if not yes:
        raise typer.Abort()
    if path.exists():
        path.unlink()
    Cache(path).initialize()
    console.print(f"Cleared cache at {datetime.now(UTC).isoformat()}")
