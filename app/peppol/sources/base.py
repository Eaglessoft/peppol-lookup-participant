from collections.abc import Awaitable, Callable
from time import perf_counter

import httpx

from app.peppol.models import SourceResult, SourceStatus


async def measured_source[T](
    source_name: str, action: Callable[[], Awaitable[T]]
) -> tuple[T | None, SourceResult]:
    started = perf_counter()
    try:
        result = await action()
        return result, SourceResult(
            source=source_name,
            status=SourceStatus.success,
            durationMs=int((perf_counter() - started) * 1000),
        )
    except httpx.TimeoutException as exc:
        return None, SourceResult(
            source=source_name,
            status=SourceStatus.timeout,
            durationMs=int((perf_counter() - started) * 1000),
            error=str(exc) or "request timed out",
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            status = SourceStatus.not_found
        elif exc.response.status_code == 429:
            status = SourceStatus.rate_limited
        else:
            status = SourceStatus.error
        return None, SourceResult(
            source=source_name,
            status=status,
            httpStatus=exc.response.status_code,
            durationMs=int((perf_counter() - started) * 1000),
            rateLimited=exc.response.status_code == 429,
            error=f"HTTP {exc.response.status_code}",
        )
    except ValueError as exc:
        return None, SourceResult(
            source=source_name,
            status=SourceStatus.invalid_response,
            durationMs=int((perf_counter() - started) * 1000),
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive source boundary
        return None, SourceResult(
            source=source_name,
            status=SourceStatus.error,
            durationMs=int((perf_counter() - started) * 1000),
            error=str(exc),
        )


def timeout_from_ms(timeout_ms: int) -> httpx.Timeout:
    seconds = max(timeout_ms, 100) / 1000
    return httpx.Timeout(seconds, connect=min(seconds, 5.0))
