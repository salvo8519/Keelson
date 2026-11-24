"""Field-level Fernet encryption for sensitive connector credentials.

Every caller keys this with ``settings.SECRET_KEY`` — keep it that way. The key
is only a *derivation input*, so any two callers using different keys produce
ciphertext the other cannot read: mixing keys silently strands rows rather than
raising at write time.

Consequence worth knowing before you rotate anything: rotating ``SECRET_KEY``
(the JWT signing key) makes every value encrypted with the old one
undecryptable. See ``app/services/mcp_connection.py`` for how that is handled.

Usage:
    from app.core.crypto import encrypt_value, decrypt_value, is_encrypted

    stored = encrypt_value(plaintext, settings.SECRET_KEY)
    original = decrypt_value(stored, settings.SECRET_KEY)
"""

import base64
import hashlib

from cryptography.fernet import Fernet, MultiFernet

_PREFIX = "enc:"


def _fernet(raw_key: str) -> Fernet:
    """Derive a valid 32-byte Fernet key from any string via SHA-256."""
    digest = hashlib.sha256(raw_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(plaintext: str, raw_key: str) -> str:
    """Encrypt *plaintext* and return a prefixed ciphertext string."""
    token = _fernet(raw_key).encrypt(plaintext.encode()).decode()
    return f"{_PREFIX}{token}"


def decrypt_value(value: str, raw_key: str) -> str:
    """Decrypt a prefixed ciphertext; return the string unchanged if not encrypted."""
    if not value.startswith(_PREFIX):
        return value
    return _fernet(raw_key).decrypt(value[len(_PREFIX):].encode()).decode()


def is_encrypted(value: object) -> bool:
    """Return True if *value* is a string produced by :func:`encrypt_value`."""
    return isinstance(value, str) and value.startswith(_PREFIX)


# --- Keelson: keys for data at rest, separate from the signing key ----------------------------
# ``DATA_ENCRYPTION_KEYS`` (newest first) encrypts secrets stored in the database. Older keys,
# and SECRET_KEY used before, still decrypt, so rotating means adding a key in front; values
# are re-encrypted with the newest key when written again (or by ``rotate_secret``). With no
# key configured (development) SECRET_KEY is used, as upstream did.


def _keys() -> list[str]:
    from app.core.config import settings

    keys = [key for key in settings.DATA_ENCRYPTION_KEYS if key]
    legacy = getattr(settings, "CHANNEL_ENCRYPTION_KEY", None)
    return [*keys, *([legacy] if legacy else []), settings.SECRET_KEY]


def _multi() -> MultiFernet:
    return MultiFernet([_fernet(key) for key in dict.fromkeys(_keys())])


def encrypt_secret(plaintext: str) -> str:
    """Encrypt with the newest data key."""
    return f"{_PREFIX}{_multi().encrypt(plaintext.encode()).decode()}"


def decrypt_secret(value: str) -> str:
    """Decrypt with any configured key; a value that is not encrypted is returned unchanged."""
    if not value.startswith(_PREFIX):
        return value
    return _multi().decrypt(value[len(_PREFIX) :].encode()).decode()


def rotate_secret(value: str) -> str:
    """The same secret encrypted with the newest data key."""
    if not value.startswith(_PREFIX):
        return encrypt_secret(value)
    return f"{_PREFIX}{_multi().rotate(value[len(_PREFIX) :].encode()).decode()}"
