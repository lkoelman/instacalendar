from pathlib import Path
from unittest.mock import Mock

from instacalendar.config import AppPaths
from instacalendar.models import ExtractionResult, InstagramPost
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

    def status(self, message: str):
        self.messages.append(message)
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


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
    fake_extractor.extract.return_value = ExtractionResult(status="not_event")
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
        "Extracting event data from post 1/1 ...",
        "Exporting approved events to ICS ...",
    ]
