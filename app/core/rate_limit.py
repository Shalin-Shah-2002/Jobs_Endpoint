from dataclasses import dataclass
from time import monotonic

from fastapi import HTTPException, Request, Response, status


@dataclass
class RateLimitState:
    count: int
    reset_at: float


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, RateLimitState] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = monotonic()
        state = self._buckets.get(key)
        if state is None or state.reset_at <= now:
            state = RateLimitState(count=0, reset_at=now + window_seconds)
            self._buckets[key] = state

        state.count += 1
        remaining = max(limit - state.count, 0)
        retry_after = max(int(state.reset_at - now), 1)
        return state.count <= limit, remaining, retry_after


def _client_key(request: Request, bucket: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{bucket}:{host}"


def read_rate_limit(request: Request, response: Response) -> None:
    settings = request.app.state.settings
    allowed, remaining, retry_after = request.app.state.rate_limiter.check(
        _client_key(request, "read"),
        settings.read_rate_limit,
        settings.rate_limit_window_seconds,
    )
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def write_rate_limit(request: Request, response: Response) -> None:
    settings = request.app.state.settings
    allowed, remaining, retry_after = request.app.state.rate_limiter.check(
        _client_key(request, "write"),
        settings.write_rate_limit,
        settings.rate_limit_window_seconds,
    )
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
