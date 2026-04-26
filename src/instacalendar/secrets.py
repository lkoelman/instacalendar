from __future__ import annotations

import keyring

SERVICE = "instacalendar"


class SecretStore:
    def get(self, name: str) -> str | None:
        try:
            return keyring.get_password(SERVICE, name)
        except keyring.errors.KeyringError:
            return None

    def set(self, name: str, value: str | None) -> None:
        if not value:
            return
        keyring.set_password(SERVICE, name, value)
