from pathlib import Path

from instacalendar.config import AppPaths
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
