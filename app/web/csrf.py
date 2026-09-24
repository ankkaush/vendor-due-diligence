"""CSRF protection for every state-changing form (security.md: "Every
state-changing form (override, approve/reject/finalize) carries a CSRF
token").

HTTP Basic auth doesn't exempt this app from CSRF: once a browser has
prompted for and cached Basic credentials for this origin, it re-attaches
them automatically to subsequent requests to that origin — including ones
triggered by a cross-site form on an attacker's page. A signed
double-submit cookie closes that gap without needing server-side session
storage: the token is set as a cookie on the page that renders the form
and also embedded as a hidden field; a POST is only accepted if the two
match AND the cookie's signature is valid and unexpired. An attacker's
cross-site form can trigger the cookie to be sent, but cannot read its
value to also set the matching hidden field.
"""

import secrets

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_MAX_AGE_SECONDS = 3600

_serializer = URLSafeTimedSerializer(settings.app_secret_key, salt="csrf")


def issue_csrf_token() -> str:
    return _serializer.dumps(secrets.token_urlsafe(16))


def _is_valid(token: str) -> bool:
    try:
        _serializer.loads(token, max_age=CSRF_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return True


class CSRFError(ValueError):
    """Raised by verify_csrf on a missing, mismatched, or invalid token —
    the caller turns this into a 403, never a silently-ignored form
    submission."""


def verify_csrf(request: Request, form_token: str) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token or not form_token:
        raise CSRFError("missing CSRF token")
    if not secrets.compare_digest(cookie_token, form_token):
        raise CSRFError("CSRF token mismatch")
    if not _is_valid(cookie_token):
        raise CSRFError("CSRF token invalid or expired")
