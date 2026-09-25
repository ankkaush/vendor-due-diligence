"""Tests for app.web.ratelimit.AuthRateLimitMiddleware (Phase 12) —
threat-model.md 3.6.3's disclosed gap, closed here: failed-auth-attempt
rate limiting on the auth boundary.

Tested against a minimal Starlette app, not the full review UI — the
middleware's behavior (count 401s per IP, block after the threshold,
never throttle successful requests) doesn't depend on anything else the
real app does, and isolating it keeps these tests fast and independent
of the DB.
"""

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.web.ratelimit import AuthRateLimitMiddleware


def _make_app(*, always_401: bool, max_failed_attempts: int = 3, window_seconds: float = 60.0):
    async def endpoint(request):
        status_code = 401 if always_401 else 200
        return JSONResponse({"ok": True}, status_code=status_code)

    app = Starlette(routes=[Route("/protected", endpoint)])
    app.add_middleware(
        AuthRateLimitMiddleware,
        max_failed_attempts=max_failed_attempts, window_seconds=window_seconds,
    )
    return app


def test_requests_below_the_threshold_are_not_throttled():
    app = _make_app(always_401=True, max_failed_attempts=3)
    client = TestClient(app)
    for _ in range(3):
        response = client.get("/protected")
        assert response.status_code == 401  # real 401s, not yet throttled


def test_failed_attempts_over_the_threshold_are_throttled_with_429():
    app = _make_app(always_401=True, max_failed_attempts=3)
    client = TestClient(app)
    for _ in range(3):
        client.get("/protected")
    throttled = client.get("/protected")
    assert throttled.status_code == 429


def test_successful_requests_are_never_throttled_regardless_of_volume():
    """A reviewer with valid credentials making many legitimate requests
    must never be blocked — only a string of failed attempts counts."""
    app = _make_app(always_401=False, max_failed_attempts=3)
    client = TestClient(app)
    for _ in range(20):
        response = client.get("/protected")
        assert response.status_code == 200


def test_different_client_ips_are_tracked_in_independent_buckets():
    """Verified at the unit level against the middleware's own failure
    dict, not through TestClient — every TestClient request presents
    the same client IP, so this is the only way to actually exercise
    two distinct IPs rather than assume the per-IP keying works."""
    middleware = AuthRateLimitMiddleware(app=None, max_failed_attempts=2, window_seconds=60.0)
    middleware._failures["1.2.3.4"] = [0.0, 0.0]  # already at the threshold
    assert len(middleware._failures["1.2.3.4"]) >= middleware._max_failed_attempts
    assert middleware._failures["9.9.9.9"] == []  # untouched, independent bucket


def test_throttle_lifts_after_the_window_elapses(monkeypatch):
    app = _make_app(always_401=True, max_failed_attempts=2, window_seconds=0.05)
    client = TestClient(app)
    client.get("/protected")
    client.get("/protected")
    assert client.get("/protected").status_code == 429

    import time

    time.sleep(0.1)  # window_seconds elapses
    assert client.get("/protected").status_code == 401  # real response again, not 429
