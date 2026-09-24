"""Single-reviewer HTTP Basic auth (deployment.md: "single-reviewer basic
auth for the review interface. No multi-user roles or permission system
— this is a portfolio automation with one reviewer persona, not an org
with an RBAC problem.").

Every route in app.web.routes depends on require_reviewer — there is no
unauthenticated route, including document content, which is embedded only
inside the already-gated case detail page (security.md: "no separate
unauthenticated file route").
"""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

_security = HTTPBasic()


def require_reviewer(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """Returns the reviewer's username on success — used as HumanReview.reviewer_id
    and AuditEvent.actor, so every write in a request is attributable to who
    made it, not just "system"."""
    valid_username = secrets.compare_digest(credentials.username, settings.reviewer_username)
    valid_password = secrets.compare_digest(credentials.password, settings.reviewer_password)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid reviewer credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
