"""FastAPI app factory for the review UI (Phase 9). Run locally with:

    uvicorn app.web.main:app --reload

No separate frontend deployment (decision #4/#8, architecture.md) — this
one ASGI app serves both the HTML routes and, later, any API surface.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.observability import configure_sentry
from app.web.ratelimit import AuthRateLimitMiddleware
from app.web.routes import router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """deployment.md's "standard security headers" middleware. HSTS is
    conditional on app_env == "production" — meaningless (and, over
    plain HTTP, actively wrong to claim) for local dev, correct once
    Phase 12 puts this behind Render's TLS termination."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


def create_app() -> FastAPI:
    configure_sentry()  # no-op without SENTRY_DSN set (observability.md)
    app = FastAPI(title="Vendor Due-Diligence — Human Review")
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuthRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_base_url],  # locked to the app's own origin, never "*"
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
