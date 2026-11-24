"""Secrets stored in the database: separate keys and rotation (Keelson)."""

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
