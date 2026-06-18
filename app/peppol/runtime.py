import asyncio
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from typing import Any

from fastapi import HTTPException, Request

from app.peppol.models import SourceResult, SourceStatus
from app.peppol.orchestrator import LookupOrchestrator
from app.shared.config import Settings


@dataclass
class CacheEntry:
    value: Any
    source_result: SourceResult
    expires_at: float


class SourceTtlCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, CacheEntry] = {}

    async def get_or_set[T](
        self,
        key: str,
        factory: Callable[[], Awaitable[tuple[T | None, SourceResult]]],
        refresh: bool,
    ) -> tuple[T | None, SourceResult]:
        now = monotonic()
        entry = self._items.get(key)
        if not refresh and entry and entry.expires_at > now:
            cached_result = entry.source_result.model_copy(deep=True)
            cached_result.durationMs = 0
            return deepcopy(entry.value), cached_result

        value, source_result = await factory()
        if source_result.status in {SourceStatus.success, SourceStatus.not_found}:
            self._items[key] = CacheEntry(
                value=deepcopy(value),
                source_result=source_result.model_copy(deep=True),
                expires_at=now + self.ttl_seconds,
            )
        return value, source_result

    def stats(self) -> dict[str, int]:
        now = monotonic()
        expired = sum(1 for entry in self._items.values() if entry.expires_at <= now)
        return {
            "ttlSeconds": self.ttl_seconds,
            "entries": len(self._items),
            "expiredEntries": expired,
        }


class LocalRateLimiter:
    def __init__(self, requests: int, window_seconds: int) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        if self.requests <= 0:
            return
        now = monotonic()
        events = self._events[key]
        while events and events[0] <= now - self.window_seconds:
            events.popleft()
        if len(events) >= self.requests:
            raise HTTPException(status_code=429, detail="local rate limit exceeded")
        events.append(now)

    def stats(self) -> dict[str, int]:
        return {
            "requests": self.requests,
            "windowSeconds": self.window_seconds,
            "trackedCallers": len(self._events),
        }


def build_orchestrator(settings: Settings) -> LookupOrchestrator:
    orchestrator = LookupOrchestrator(settings)
    if settings.peppol_codelist_required and not orchestrator.codelists.loaded_from_cache:
        raise RuntimeError(
            "PEPPOL_CODELIST_REQUIRED is true but no valid codelist cache was loaded"
        )
    orchestrator.source_cache = SourceTtlCache(settings.peppol_cache_ttl_seconds)
    return orchestrator


def build_rate_limiter(settings: Settings) -> LocalRateLimiter:
    return LocalRateLimiter(
        settings.peppol_rate_limit_requests,
        settings.peppol_rate_limit_window_seconds,
    )


def get_orchestrator_from_request(request: Request) -> LookupOrchestrator:
    return request.app.state.lookup_orchestrator


def enforce_rate_limit(request: Request) -> None:
    limiter: LocalRateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    client_host = request.client.host if request.client else "unknown"
    limiter.check(client_host)


async def codelist_refresh_loop(orchestrator: LookupOrchestrator, interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await orchestrator.refresh_codelists()
        except Exception:
            # Refresh is best-effort; the evaluator keeps using the last valid cache.
            continue
