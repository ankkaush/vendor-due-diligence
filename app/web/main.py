"""FastAPI app factory for the review UI (Phase 9). Run locally with:

    uvicorn app.web.main:app --reload

No separate frontend deployment (decision #4/#8, architecture.md) — this
one ASGI app serves both the HTML routes and, later, any API surface.
"""

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.web.routes import router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """The subset of deployment.md's "standard security headers" that's
    meaningful before Phase 12 puts this behind Render's TLS termination —
    HSTS is deliberately not added here since that's a production/HTTPS
    concern, not a local-dev one."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="Vendor Due-Diligence — Human Review")
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(router)
    return app


app = create_app()
