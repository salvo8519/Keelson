"""In-memory stand-ins for the services some tests do not run (Keelstone)."""

import time


class MemoryRedis:
    """The few Redis operations the sign-in routes use (app/core/revoked_tokens.py), in memory.

    Lifetimes are recorded in ``ttls`` but not applied. ``now`` is the clock of this Redis
    (``TIME``): a test that needs time to pass moves it.
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.now = time.time()

    async def set(self, key: str, value: str, ttl: int | None = None, *, only_if_absent: bool = False) -> bool:
        if only_if_absent and key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ttl
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def time(self) -> float:
        return self.now


OPERATIONS = ("set", "get", "exists", "time")


class FailingRedis:
    """A ``MemoryRedis`` whose named operations fail as an unreachable Redis does; the others
    work. ``FailingRedis(*OPERATIONS)`` is a Redis that does not answer at all."""

    def __init__(self, *failing: str) -> None:
        assert set(failing) <= set(OPERATIONS), failing
        self.inner = MemoryRedis()
        self.failing = set(failing)

    def _check(self, operation: str) -> None:
        if operation in self.failing:
            raise ConnectionError("redis unavailable")

    async def set(self, key: str, value: str, ttl: int | None = None, *, only_if_absent: bool = False) -> bool:
        self._check("set")
        return await self.inner.set(key, value, ttl, only_if_absent=only_if_absent)

    async def get(self, key: str) -> str | None:
        self._check("get")
        return await self.inner.get(key)

    async def exists(self, key: str) -> bool:
        self._check("exists")
        return await self.inner.exists(key)

    async def time(self) -> float:
        self._check("time")
        return await self.inner.time()


class DownRedis(FailingRedis):
    """A Redis that does not answer at all (an outage)."""

    def __init__(self) -> None:
        super().__init__(*OPERATIONS)
