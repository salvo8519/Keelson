"""Secrets stored in the database: separate keys and rotation (Keelstone)."""

import pytest
from cryptography.fernet import InvalidToken

from app.core import crypto
from app.core.config import settings

OLD = "a" * 64
NEW = "b" * 64


def test_secrets_are_encrypted_and_never_stored_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", [NEW])
    stored = crypto.encrypt_secret("client-secret-value")
    assert stored.startswith("enc:") and "client-secret-value" not in stored
    assert crypto.decrypt_secret(stored) == "client-secret-value"


def test_a_new_key_in_front_still_reads_old_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", [OLD])
    stored = crypto.encrypt_secret("token")
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", [NEW, OLD])
    assert crypto.decrypt_secret(stored) == "token"
    rotated = crypto.rotate_secret(stored)
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", [NEW])
    assert crypto.decrypt_secret(rotated) == "token"
    with pytest.raises(InvalidToken):
        crypto.decrypt_secret(stored)


def test_values_written_before_the_data_keys_still_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = crypto.encrypt_value("token", settings.SECRET_KEY)
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", [NEW])
    assert crypto.decrypt_secret(legacy) == "token"


def test_the_setting_accepts_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_ENCRYPTION_KEYS", f"{NEW}, {OLD}")
    assert type(settings)().DATA_ENCRYPTION_KEYS == [NEW, OLD]


def test_a_value_that_is_not_encrypted_is_encrypted_by_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEYS", [NEW])
    rotated = crypto.rotate_secret("plain-value")
    assert crypto.is_encrypted(rotated) and "plain-value" not in rotated
    assert crypto.decrypt_secret(rotated) == "plain-value"


def test_values_of_the_legacy_channel_key_still_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Renders with channels encrypted with ``CHANNEL_ENCRYPTION_KEY`` before the data keys."""
    from types import SimpleNamespace

    from app.core import config

    legacy_key = "c" * 64
    stored = crypto.encrypt_value("bot-token", legacy_key)
    stub = SimpleNamespace(DATA_ENCRYPTION_KEYS=[NEW], CHANNEL_ENCRYPTION_KEY=legacy_key, SECRET_KEY=OLD)
    monkeypatch.setattr(config, "settings", stub)
    assert crypto.decrypt_secret(stored) == "bot-token"


def test_only_prefixed_strings_count_as_encrypted() -> None:
    stored = crypto.encrypt_value("value", OLD)
    assert crypto.is_encrypted(stored)
    assert not crypto.is_encrypted("value")
    assert not crypto.is_encrypted(None)
    assert not crypto.is_encrypted(b"enc:bytes")


def test_the_single_key_helpers_round_trip_and_pass_plain_text_through() -> None:
    stored = crypto.encrypt_value("value", OLD)
    assert crypto.decrypt_value(stored, OLD) == "value"
    assert crypto.decrypt_value("value", OLD) == "value"
    with pytest.raises(InvalidToken):
        crypto.decrypt_value(stored, NEW)
