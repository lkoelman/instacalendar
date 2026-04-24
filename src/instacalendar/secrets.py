from __future__ import annotations

import json
from pathlib import Path

import keyring

SERVICE = "instacalendar"


class SecretStore:
    def __init__(self, fallback_file: Path) -> None:
        self.fallback_file = fallback_file

    def get(self, name: str) -> str | None:
        try:
            value = keyring.get_password(SERVICE, name)
        except keyring.errors.KeyringError:
            value = None
        return value or self._load_fallback().get(name)

    def set(self, name: str, value: str | None) -> None:
        if not value:
            return
        try:
            keyring.set_password(SERVICE, name, value)
            return
        except keyring.errors.KeyringError:
            pass
        data = self._load_fallback()
        data[name] = value
        self.fallback_file.parent.mkdir(parents=True, exist_ok=True)
        self.fallback_file.write_text(json.dumps(data, indent=2) + "\n")

    def _load_fallback(self) -> dict[str, str]:
        if not self.fallback_file.exists():
            return {}
        return json.loads(self.fallback_file.read_text())
