"""Failed-auth-attempt rate limiting (Phase 12, closing threat-model.md
3.6.3's disclosed gap: "residual risk accepted for a single-user
portfolio system but not left completely unmitigated").

In-memory, per-process — deliberately, matching architecture.md's "no
Redis" constraint and this app's single-instance deployment (Render
free tier, no autoscaling). A distributed rate limiter would be solving
a scaling problem this project doesn't have.

Counts failed (401) responses per client IP, not every request — a
reviewer with valid credentials making many legitimate requests should
never be throttled; only a string of wrong-credential attempts should.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MAX_FAILED_ATTEMPTS = 10
WINDOW_SECONDS = 60.0


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app, *, max_failed_attempts: int = MAX_FAILED_ATTEMPTS,
        window_seconds: float = WINDOW_SECONDS,
    ):
        super().__init__(app)
        self._max_failed_attempts = max_failed_attempts
        self._window_seconds = window_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        recent = [t for t in self._failures[client_ip] if now - t < self._window_seconds]
        if len(recent) >= self._max_failed_attempts:
            self._failures[client_ip] = recent
            return JSONResponse(
                {"detail": "Too many failed authentication attempts. Try again later."},
                status_code=429,
            )

        response = await call_next(request)

        if response.status_code == 401:
            recent.append(now)
        self._failures[client_ip] = recent
        return response
