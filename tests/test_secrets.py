from unittest.mock import patch

import keyring

from instacalendar.secrets import SecretStore


def test_tests_use_in_memory_keyring_backend():
    store = SecretStore()

    store.set("roundtrip-key", "secret-value")

    assert keyring.get_keyring().__class__.__name__ == "InMemoryKeyring"
    assert store.get("roundtrip-key") == "secret-value"


def test_secret_store_uses_keyring():
    store = SecretStore()

    with patch("keyring.get_password") as mock_get:
        mock_get.return_value = "secret-value"
        assert store.get("my-key") == "secret-value"
        mock_get.assert_called_once_with("instacalendar", "my-key")


def test_secret_store_saves_to_keyring():
    store = SecretStore()

    with patch("keyring.set_password") as mock_set:
        store.set("my-key", "new-value")
        mock_set.assert_called_once_with("instacalendar", "my-key", "new-value")


def test_secret_store_returns_none_on_keyring_error():
    store = SecretStore()
    import keyring

    with patch("keyring.get_password") as mock_get:
        mock_get.side_effect = keyring.errors.KeyringError("test error")
        assert store.get("my-key") is None
