"""API keys of organizations: format, hashing and scopes (Keelstone).

A key is shown once, at creation, as ``<prefix>.<secret>``:

* the prefix (``key_`` and 12 random characters) identifies the key; it is stored in clear and
  shown in the interface, so a key can be recognised without revealing it;
* the secret (43 random characters) is never stored: the database keeps its HMAC-SHA256 with
  the server's ``SECRET_KEY``, so a copy of the database cannot be replayed as a key.

Pure functions only: no database, no settings import. Callers pass the server key.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

PREFIX_TAG = "key_"
PREFIX_RANDOM_LENGTH = 12
SECRET_BYTES = 32
SEPARATOR = "."

# Rotation keeps the previous key valid for a grace period, so clients can switch over.
DEFAULT_ROTATION_GRACE = timedelta(hours=1)
MAX_ROTATION_GRACE = timedelta(days=7)

# last_used_at is written at most once per interval per key, to keep authentication cheap.
LAST_USED_RESOLUTION = timedelta(minutes=1)

# Scopes an organization can grant to a key. Extend this mapping when you protect a new area
# with ``require_api_scopes``; the descriptions are shown in the interface.
SCOPES: dict[str, str] = {
    "conversations:read": "Read conversations and messages",
    "conversations:write": "Create conversations and send messages",
    "knowledge:read": "Search and read knowledge bases",
    "knowledge:write": "Upload documents to knowledge bases",
    "agent:run": "Run the agent",
}


def generate() -> tuple[str, str, str]:
    """A new key: ``(prefix, secret, token)``, where ``token`` is what the client sends."""
    prefix = PREFIX_TAG + secrets.token_urlsafe(PREFIX_RANDOM_LENGTH)[:PREFIX_RANDOM_LENGTH]
    secret = secrets.token_urlsafe(SECRET_BYTES)
    return prefix, secret, f"{prefix}{SEPARATOR}{secret}"


def parse(token: str) -> tuple[str, str] | None:
    """``(prefix, secret)`` of a well-formed token, otherwise None."""
    prefix, separator, secret = token.strip().partition(SEPARATOR)
    if not separator or not prefix.startswith(PREFIX_TAG) or not secret:
        return None
    if len(prefix) != len(PREFIX_TAG) + PREFIX_RANDOM_LENGTH:
        return None
    return prefix, secret


def hash_secret(secret: str, server_key: str) -> str:
    """HMAC-SHA256 of the secret with the server key, hex encoded."""
    return hmac.new(server_key.encode(), secret.encode(), hashlib.sha256).hexdigest()


def secret_matches(secret: str, stored_hash: str, server_key: str) -> bool:
    """Constant-time check of a secret against its stored hash."""
    return hmac.compare_digest(hash_secret(secret, server_key), stored_hash)


def unknown_scopes(scopes: list[str]) -> list[str]:
    """Scopes not in ``SCOPES``, in the order given."""
    return [scope for scope in scopes if scope not in SCOPES]
