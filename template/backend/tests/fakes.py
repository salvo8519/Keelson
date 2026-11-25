"""In-memory stand-ins for the services some tests do not run (Keelstone)."""


class MemoryRedis:
    """The few Redis operations the sign-in routes use (app/core/revoked_tokens.py), in memory.

    Lifetimes are not applied: a test that needs a key to expire moves the clock of the module
    that reads it instead.
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def exists(self, key: str) -> bool:
        return key in self.values
