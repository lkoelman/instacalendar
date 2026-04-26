from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock

from instacalendar.config import AppPaths
from instacalendar.extractors.openrouter import ModelUsage
from instacalendar.models import (
    EventDraft,
    ExtractionResult,
    ImageReference,
    InstagramPost,
    VideoReference,
)
from instacalendar.runner import AppRunner


class FakePrompt:
    def __init__(self, *, confirm_answer: bool) -> None:
        self.confirm_answer = confirm_answer
        self.text_messages: list[str] = []
        self.confirm_messages: list[str] = []

    def text(self, message: str, *, default: str | None = None, password: bool = False) -> str:
        self.text_messages.append(message)
        values = {
            "Instagram username": "musicfan",
            "Instagram password": "instagram-secret",
            "OpenRouter API key": "typed-openrouter-key",
            "OpenRouter text model": default or "text",
            "OpenRouter vision model": default or "vision",
            "OpenRouter video model": default or "video",
        }
        return values[message]

    def choose(self, message: str, choices: list[str], *, default: str | None = None) -> str:
        return choices[0]

    def confirm(self, message: str, *, default: bool = True) -> bool:
        self.confirm_messages.append(message)
        return self.confirm_answer


class FakeProgress:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.tasks: list[tuple[str, int]] = []
        self.task_updates: list[str] = []
        self.task_reports: list[str] = []
        self.task_advances = 0

    def status(self, message: str):
        self.messages.append(message)
        return self

    def task(self, description: str, *, total: int):
        self.tasks.append((description, total))
        return self

    def update(self, message: str) -> None:
        self.task_updates.append(message)

    def advance(self) -> None:
        self.task_advances += 1

    def report(self, message: str) -> None:
        self.task_reports.append(message)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class ReviewPrompt(FakePrompt):
    def __init__(self, progress: "ReviewProgress") -> None:
        super().__init__(confirm_answer=True)
        self.progress = progress
        self.review_prompt_saw_active_task = False

    def confirm(self, message: str, *, default: bool = True) -> bool:
        if message.startswith("Use OPENROUTER_API_KEY"):
            return super().confirm(message, default=default)
        self.review_prompt_saw_active_task = self.progress.task_active
        return super().confirm(message, default=default)


class ReviewProgress:
    def __init__(self) -> None:
        self.task_active = False
        self.tasks: list[tuple[str, int]] = []

    def status(self, message: str):
        return self

    def task(self, description: str, *, total: int):
        self.tasks.append((description, total))
        return self

    def update(self, message: str) -> None:
        return None

    def advance(self) -> None:
        return None

    def report(self, message: str) -> None:
        return None

    def __enter__(self):
        if self.tasks:
            self.task_active = True
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.task_active = False


def test_configure_asks_to_use_openrouter_api_key_from_environment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-openrouter-key")
    prompt = FakePrompt(confirm_answer=True)
    runner = AppRunner(AppPaths.from_base(tmp_path), prompt)

    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    assert prompt.confirm_messages == ["Use OPENROUTER_API_KEY from your environment?"]
    assert "OpenRouter API key" not in prompt.text_messages
    assert runner.secret_store.get("openrouter_api_key") == "env-openrouter-key"


def test_configure_prompts_for_openrouter_key_when_environment_key_declined(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-openrouter-key")
    prompt = FakePrompt(confirm_answer=False)
    runner = AppRunner(AppPaths.from_base(tmp_path), prompt)

    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    assert prompt.confirm_messages == ["Use OPENROUTER_API_KEY from your environment?"]
    assert "OpenRouter API key" in prompt.text_messages
    assert runner.secret_store.get("openrouter_api_key") == "typed-openrouter-key"


def test_run_reports_progress_for_instagram_extraction_and_export(
    tmp_path: Path, monkeypatch
) -> None:
    paths = AppPaths.from_base(tmp_path)
    progress = FakeProgress()
    runner = AppRunner(paths, FakePrompt(confirm_answer=True), progress=progress)
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            self.username = username
            self.password = password
            self.session_file = session_file

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [
                InstagramPost(
                    media_pk="1",
                    shortcode="abc",
                    caption="not an event",
                    media_kind="image",
                )
            ]

    fake_extractor = Mock()

    def fake_extract(post: InstagramPost, *, status_callback, usage_callback=None):
        status_callback("Interpreting post text")
        return ExtractionResult(status="not_event")

    fake_extractor.extract.side_effect = fake_extract
    fake_exporter = Mock()
    fake_exporter.export.return_value = []

    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr(
        "instacalendar.runner.IcsExporter",
        lambda: fake_exporter,
    )

    runner.run(ics_output=tmp_path / "events.ics")

    assert progress.messages == [
        "Initializing cache ...",
        "Loading configuration ...",
        "Authenticating with Instagram ...",
        "Fetching collections ...",
        "Fetching posts from Concerts ...",
        "Caching posts from Concerts ...",
        "Exporting approved events to ICS ...",
    ]
    assert progress.tasks == [("Processing posts", 1)]
    assert progress.task_updates == ["Post 1/1: Interpreting post text"]
    assert progress.task_reports == ["@unknown (unknown date) - failed - no event details"]
    assert progress.task_advances == 1
    fake_extractor.extract.assert_called_once()
    assert fake_extractor.extract.call_args.kwargs["status_callback"] is not None

    assert runner.cache.load_cached_posts("Concerts")[0].media_pk == "1"


def test_run_reviews_events_after_processing_progress_task_exits(
    tmp_path: Path, monkeypatch
) -> None:
    paths = AppPaths.from_base(tmp_path)
    progress = ReviewProgress()
    prompt = ReviewPrompt(progress)
    runner = AppRunner(paths, prompt, progress=progress)
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )
    runner.cache.initialize()
    runner.cache.upsert_cached_post(
        collection_name="Concerts",
        post=InstagramPost(media_pk="1", caption="Live Set", media_kind="image"),
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        media=[],
    )

    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(
        status="event",
        events=[
            EventDraft(
                title="Live Set",
                start=datetime(2026, 5, 3, 20, 0, tzinfo=UTC),
            )
        ],
    )
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(collection="Concerts", from_cache=True, ics_output=tmp_path / "events.ics")

    assert prompt.review_prompt_saw_active_task is False


def test_run_reports_runtime_extraction_costs_by_model(tmp_path: Path, monkeypatch) -> None:
    paths = AppPaths.from_base(tmp_path)
    progress = FakeProgress()
    runner = AppRunner(paths, FakePrompt(confirm_answer=True), progress=progress)
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="not an event", media_kind="image")]

    fake_extractor = Mock()

    def fake_extract(post: InstagramPost, *, status_callback, usage_callback):
        status_callback("Interpreting post text")
        usage_callback(
            ModelUsage(
                model="text",
                prompt_tokens=100,
                completion_tokens=25,
                total_tokens=125,
                estimated_cost_usd=0.001,
            )
        )
        return ExtractionResult(status="not_event")

    fake_extractor.extract.side_effect = fake_extract
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    summary = runner.run(ics_output=tmp_path / "events.ics")

    assert any("post est. $0.0010" in update for update in progress.task_updates)
    assert progress.task_reports == [
        "@unknown (unknown date) - failed - no event details - "
        "post est. $0.0010; run est. $0.0010; text: 125 tokens ($0.0010)"
    ]
    assert summary.extraction_usage_by_model["text"].total_tokens == 125
    assert summary.extraction_usage_by_model["text"].estimated_cost_usd == 0.001


def test_run_reports_completed_post_with_event_source_and_details(
    tmp_path: Path, monkeypatch
) -> None:
    paths = AppPaths.from_base(tmp_path)
    progress = FakeProgress()
    runner = AppRunner(paths, FakePrompt(confirm_answer=True), progress=progress)
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [
                InstagramPost(
                    media_pk="1",
                    poster_username="venue",
                    taken_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                    caption="Live Set",
                    media_kind="image",
                )
            ]

    fake_extractor = Mock()

    def fake_extract(post: InstagramPost, *, status_callback, usage_callback=None):
        status_callback("Interpreting post text")
        status_callback("Falling back to image")
        status_callback("Interpreting image")
        return ExtractionResult(
            status="event",
            events=[
                EventDraft(
                    title="Live Set",
                    start=datetime(2026, 5, 3, 20, 0, tzinfo=UTC),
                    location_name="The Room",
                )
            ],
        )

    fake_extractor.extract.side_effect = fake_extract
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics")

    assert progress.task_reports == [
        "@venue (2026-04-02) - Identified event details from image => 2026-05-03 at The Room"
    ]


def test_run_reports_completed_post_from_video_fallback(tmp_path: Path, monkeypatch) -> None:
    paths = AppPaths.from_base(tmp_path)
    progress = FakeProgress()
    runner = AppRunner(paths, FakePrompt(confirm_answer=True), progress=progress)
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
        openrouter_video_model="video",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [
                InstagramPost(
                    media_pk="1",
                    poster_username="venue",
                    taken_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                    caption="Live Set",
                    media_kind="video",
                )
            ]

    fake_extractor = Mock()

    def fake_extract(post: InstagramPost, *, status_callback, usage_callback=None):
        status_callback("Interpreting post text")
        status_callback("Falling back to video")
        status_callback("Interpreting video")
        return ExtractionResult(
            status="event",
            events=[
                EventDraft(
                    title="Live Set",
                    start=datetime(2026, 5, 3, 20, 0, tzinfo=UTC),
                    location_name="The Room",
                )
            ],
        )

    fake_extractor.extract.side_effect = fake_extract
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics")

    assert progress.task_reports == [
        "@venue (2026-04-02) - Identified event details from video => 2026-05-03 at The Room"
    ]


def test_run_passes_configured_video_model_to_extractor(tmp_path: Path, monkeypatch) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
        openrouter_video_model="video",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="", media_kind="video")]

    extractor_kwargs = {}
    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(status="not_event")

    def fake_extractor_factory(**kwargs):
        extractor_kwargs.update(kwargs)
        return fake_extractor

    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr("instacalendar.runner.OpenRouterExtractor", fake_extractor_factory)
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics")

    assert extractor_kwargs["video_model"] == "video"


def test_run_uses_vision_model_for_video_when_config_has_no_video_model(
    tmp_path: Path, monkeypatch
) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="", media_kind="video")]

    extractor_kwargs = {}
    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(status="not_event")

    def fake_extractor_factory(**kwargs):
        extractor_kwargs.update(kwargs)
        return fake_extractor

    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr("instacalendar.runner.OpenRouterExtractor", fake_extractor_factory)
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics")

    assert extractor_kwargs["video_model"] == "vision"


def test_run_filters_posts_by_posted_since(tmp_path: Path, monkeypatch) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [
                InstagramPost(
                    media_pk="old",
                    taken_at=datetime(2026, 3, 31, 12, 0, tzinfo=UTC),
                    media_kind="image",
                ),
                InstagramPost(
                    media_pk="on-date",
                    taken_at=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
                    media_kind="image",
                ),
                InstagramPost(
                    media_pk="later",
                    taken_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                    media_kind="image",
                ),
                InstagramPost(media_pk="missing-date", media_kind="image"),
            ]

    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(status="not_event")
    fake_exporter = Mock()
    fake_exporter.export.return_value = []

    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: fake_exporter)

    summary = runner.run(ics_output=tmp_path / "events.ics", posted_since=date(2026, 4, 1))

    assert [call.args[0].media_pk for call in fake_extractor.extract.call_args_list] == [
        "on-date",
        "later",
    ]
    assert [post.media_pk for post in runner.cache.load_cached_posts("Concerts")] == [
        "on-date",
        "later",
    ]
    assert summary.processed_posts == 2


def test_run_caches_successful_media_and_keeps_post_when_media_download_fails(
    tmp_path: Path, monkeypatch
) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [
                InstagramPost(
                    media_pk="1",
                    shortcode="abc",
                    caption="Live Set",
                    media_kind="image",
                    images=[ImageReference(uri="https://cdn.example/post.jpg")],
                    videos=[VideoReference(uri="https://cdn.example/post.mp4")],
                )
            ]

    class FakeResponse:
        content = b"image bytes"

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **kwargs):
        if url.endswith(".mp4"):
            raise RuntimeError("video failed")
        return FakeResponse()

    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(status="not_event")
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr("instacalendar.runner.httpx.get", fake_get)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics")

    cached_post = runner.cache.load_cached_posts("Concerts")[0]
    assert Path(cached_post.images[0].uri).exists()
    assert cached_post.videos[0].uri == "https://cdn.example/post.mp4"
    summary = runner.cache.list_cached_posts()[0]
    assert summary.cached_images == 1
    assert summary.cached_videos == 0
    assert summary.missing_media == 1


def test_run_applies_limit_after_posted_since_filter(tmp_path: Path, monkeypatch) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [
                InstagramPost(
                    media_pk="old",
                    taken_at=datetime(2026, 3, 31, 12, 0, tzinfo=UTC),
                    media_kind="image",
                ),
                InstagramPost(
                    media_pk="first-match",
                    taken_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
                    media_kind="image",
                ),
                InstagramPost(
                    media_pk="second-match",
                    taken_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
                    media_kind="image",
                ),
            ]

    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(status="not_event")

    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    summary = runner.run(
        ics_output=tmp_path / "events.ics",
        posted_since=date(2026, 4, 1),
        limit=1,
    )

    assert [call.args[0].media_pk for call in fake_extractor.extract.call_args_list] == [
        "first-match"
    ]
    assert [post.media_pk for post in runner.cache.load_cached_posts("Concerts")] == [
        "first-match"
    ]
    assert summary.processed_posts == 1


def test_run_from_cache_bypasses_instagram_and_extracts_cached_posts(
    tmp_path: Path, monkeypatch
) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )
    runner.cache.initialize()
    runner.cache.upsert_cached_post(
        collection_name="Concerts",
        post=InstagramPost(
            media_pk="1",
            shortcode="abc",
            caption="Live Set May 3",
            media_kind="image",
            images=[ImageReference(uri=str(tmp_path / "poster.jpg"))],
        ),
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        media=[],
    )

    class FailingInstagramClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("Instagram should not be used")

    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(
        status="event",
        events=[
            EventDraft(
                title="Live Set",
                start=datetime(2026, 5, 3, 20, 0, tzinfo=UTC),
            )
        ],
    )
    fake_exporter = Mock()
    fake_exporter.export.return_value = []

    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FailingInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: fake_exporter)

    summary = runner.run(
        collection="Concerts",
        from_cache=True,
        ics_output=tmp_path / "events.ics",
    )

    assert summary.processed_posts == 1
    assert summary.exported_events == 1
    assert fake_extractor.extract.call_args.args[0].media_pk == "1"


def test_run_from_cache_prompts_for_cached_collection(tmp_path: Path, monkeypatch) -> None:
    prompt = FakePrompt(confirm_answer=True)
    runner = AppRunner(AppPaths.from_base(tmp_path), prompt)
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )
    runner.cache.initialize()
    runner.cache.upsert_cached_post(
        collection_name="Concerts",
        post=InstagramPost(media_pk="1", caption="", media_kind="image"),
        fetched_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        media=[],
    )

    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(status="not_event")
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(from_cache=True, ics_output=tmp_path / "events.ics")

    assert fake_extractor.extract.call_args.args[0].media_pk == "1"


def test_run_from_cache_fails_when_collection_has_no_posts(tmp_path: Path) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    try:
        runner.run(from_cache=True, collection="Missing", ics_output=tmp_path / "events.ics")
    except RuntimeError as error:
        assert "No cached posts found" in str(error)
    else:
        raise AssertionError("expected RuntimeError")


def test_run_reuses_cached_extraction_result_without_calling_openrouter(
    tmp_path: Path, monkeypatch
) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )
    runner.cache.initialize()
    model_signature = runner.cache.extraction_model_signature(
        text_model="text",
        vision_model="vision",
        video_model="vision",
    )
    runner.cache.record_extraction_result(
        media_pk="1",
        model_signature=model_signature,
        source_media_kind="text",
        result=ExtractionResult(
            status="event",
            events=[
                EventDraft(
                    title="Cached Show",
                    start=datetime(2026, 5, 3, 20, 0, tzinfo=UTC),
                )
            ],
            model_ids=["text"],
        ),
        extracted_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="Live Set", media_kind="image")]

    fake_extractor = Mock()
    fake_exporter = Mock()
    fake_exporter.export.return_value = []
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: fake_exporter)

    summary = runner.run(ics_output=tmp_path / "events.ics")

    fake_extractor.extract.assert_not_called()
    assert summary.exported_events == 1


def test_run_ignore_event_cache_forces_extraction_and_updates_cache(
    tmp_path: Path, monkeypatch
) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )
    runner.cache.initialize()
    model_signature = runner.cache.extraction_model_signature(
        text_model="text",
        vision_model="vision",
        video_model="vision",
    )
    runner.cache.record_extraction_result(
        media_pk="1",
        model_signature=model_signature,
        source_media_kind="text",
        result=ExtractionResult(status="not_event", model_ids=["text"]),
        extracted_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="Live Set", media_kind="image")]

    fake_extractor = Mock()

    def fake_extract(post: InstagramPost, *, status_callback, usage_callback=None):
        status_callback("Interpreting post text")
        status_callback("Falling back to image")
        status_callback("Interpreting image")
        return ExtractionResult(
            status="event",
            events=[
                EventDraft(
                    title="Fresh Show",
                    start=datetime(2026, 5, 4, 20, 0, tzinfo=UTC),
                )
            ],
            model_ids=["vision"],
        )

    fake_extractor.extract.side_effect = fake_extract
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics", ignore_event_cache=True)

    fake_extractor.extract.assert_called_once()
    cached = runner.cache.get_extraction_result(
        media_pk="1",
        model_signature=model_signature,
        source_media_kind="image",
        event_cache_key="model,media",
    )
    assert cached is not None
    assert cached.events[0].title == "Fresh Show"


def test_run_default_event_cache_key_misses_when_models_change(
    tmp_path: Path, monkeypatch
) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text-v2",
        openrouter_vision_model="vision",
    )
    runner.cache.initialize()
    old_signature = runner.cache.extraction_model_signature(
        text_model="text-v1",
        vision_model="vision",
        video_model="vision",
    )
    runner.cache.record_extraction_result(
        media_pk="1",
        model_signature=old_signature,
        source_media_kind="text",
        result=ExtractionResult(status="not_event", model_ids=["text-v1"]),
        extracted_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="Live Set", media_kind="image")]

    fake_extractor = Mock()
    fake_extractor.extract.return_value = ExtractionResult(
        status="not_event", model_ids=["text-v2"]
    )
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics")

    fake_extractor.extract.assert_called_once()


def test_run_post_media_event_cache_key_reuses_across_model_changes(
    tmp_path: Path, monkeypatch
) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text-v2",
        openrouter_vision_model="vision",
    )
    runner.cache.initialize()
    old_signature = runner.cache.extraction_model_signature(
        text_model="text-v1",
        vision_model="vision",
        video_model="vision",
    )
    runner.cache.record_extraction_result(
        media_pk="1",
        model_signature=old_signature,
        source_media_kind="text",
        result=ExtractionResult(status="not_event", model_ids=["text-v1"]),
        extracted_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="Live Set", media_kind="image")]

    fake_extractor = Mock()
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )
    monkeypatch.setattr("instacalendar.runner.IcsExporter", lambda: Mock(export=Mock()))

    runner.run(ics_output=tmp_path / "events.ics", event_cache_key="post,media")

    fake_extractor.extract.assert_not_called()


def test_run_does_not_cache_extraction_failures(tmp_path: Path, monkeypatch) -> None:
    runner = AppRunner(AppPaths.from_base(tmp_path), FakePrompt(confirm_answer=True))
    runner.configure(
        instagram_username="musicfan",
        instagram_password="instagram-secret",
        openrouter_api_key="openrouter-secret",
        openrouter_text_model="text",
        openrouter_vision_model="vision",
    )

    class FakeInstagramClient:
        def __init__(self, username: str, password: str, session_file: Path) -> None:
            return None

        def authenticate(self) -> None:
            return None

        def list_collections(self) -> list[str]:
            return ["Concerts"]

        def fetch_collection_posts(self, collection_name: str) -> list[InstagramPost]:
            return [InstagramPost(media_pk="1", caption="Live Set", media_kind="image")]

    fake_extractor = Mock()
    fake_extractor.extract.side_effect = RuntimeError("OpenRouter failed")
    monkeypatch.setattr("instacalendar.runner.LiveInstagramClient", FakeInstagramClient)
    monkeypatch.setattr(
        "instacalendar.runner.OpenRouterExtractor",
        lambda **kwargs: fake_extractor,
    )

    try:
        runner.run(ics_output=tmp_path / "events.ics")
    except RuntimeError as error:
        assert "OpenRouter failed" in str(error)
    else:
        raise AssertionError("expected RuntimeError")

    model_signature = runner.cache.extraction_model_signature(
        text_model="text",
        vision_model="vision",
        video_model="vision",
    )
    assert runner.cache.get_extraction_result(
        media_pk="1",
        model_signature=model_signature,
        source_media_kind="text",
        event_cache_key="model,media",
    ) is None
