"""HTTP routes for the human review UI (Phase 9, architecture.md's
AWAITING_HUMAN_REVIEW -> FINALIZED step — the one transition the system
never makes on its own).

Every route depends on require_reviewer (auth.py) — there is no
unauthenticated route. The review submission is the only state-changing
endpoint and is CSRF-protected (csrf.py) and idempotent under a concurrent
double-submit: the state-machine's WHERE-guarded transition_case() is the
same guard app.state_machine already proved under real concurrency in
Phase 5, reused here rather than re-invented for this one more caller.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.audit import record_event
from app.db.models import HumanReview, HumanReviewOverride
from app.state_machine import transition_case
from app.web.auth import require_reviewer
from app.web.csrf import CSRF_COOKIE_NAME, CSRFError, issue_csrf_token, verify_csrf
from app.web.deps import get_db
from app.web.queries import get_case_detail, list_cases

router = APIRouter()
templates = Jinja2Templates(directory=str(__file__.rsplit("/", 1)[0] + "/templates"))

VALID_DECISIONS = {"approved", "rejected", "conditional", "needs_more_info"}


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/cases", status_code=status.HTTP_302_FOUND)


@router.get("/cases", response_class=HTMLResponse)
def cases_list(
    request: Request,
    db: Session = Depends(get_db),
    reviewer: str = Depends(require_reviewer),
) -> HTMLResponse:
    cases = list_cases(db)
    return templates.TemplateResponse(
        request, "case_list.html", {"cases": cases, "reviewer": reviewer},
    )


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail(
    request: Request,
    case_id: UUID,
    db: Session = Depends(get_db),
    reviewer: str = Depends(require_reviewer),
) -> HTMLResponse:
    detail = get_case_detail(db, case_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    csrf_token = issue_csrf_token()
    response = templates.TemplateResponse(
        request, "case_detail.html",
        {
            "detail": detail, "reviewer": reviewer, "csrf_token": csrf_token,
            "valid_decisions": sorted(VALID_DECISIONS),
        },
    )
    response.set_cookie(
        CSRF_COOKIE_NAME, csrf_token, httponly=True, samesite="lax", max_age=3600,
    )
    return response


@router.post("/cases/{case_id}/review")
def submit_review(
    request: Request,
    case_id: UUID,
    csrf_token: str = Form(...),
    decision: str = Form(...),
    comments: str = Form(""),
    override_finding_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
    reviewer: str = Depends(require_reviewer),
) -> RedirectResponse:
    try:
        verify_csrf(request, csrf_token)
    except CSRFError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if decision not in VALID_DECISIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"decision must be one of {sorted(VALID_DECISIONS)}",
        )

    detail = get_case_detail(db, case_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not detail.can_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Case is {detail.case.status}, not AWAITING_HUMAN_REVIEW — "
                   "already reviewed or not ready yet.",
        )

    valid_finding_ids = {str(fid) for fid in detail.all_finding_ids}
    overridden = [fid for fid in override_finding_ids if fid in valid_finding_ids]

    review = HumanReview(
        case_id=case_id, reviewer_id=reviewer, decision=decision,
        comments=comments or None,
    )
    db.add(review)
    db.flush()
    for finding_id in overridden:
        db.add(HumanReviewOverride(human_review_id=review.id, finding_id=UUID(finding_id)))

    applied = transition_case(
        db, case_id, from_status="AWAITING_HUMAN_REVIEW", to_status="FINALIZED",
        actor=reviewer,
    )
    if not applied:
        # Lost a race against a concurrent reviewer/duplicate submit — the
        # same "someone else already handled it" outcome
        # app.intake.mark_documents_ready documents. Roll back this
        # review row rather than record a decision against a case that
        # someone else already finalized differently.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Case was already finalized by another review submission.",
        )

    detail.case.finalized_at = datetime.now(UTC)
    record_event(
        db, case_id=case_id, event_type="human_review.recorded", actor=reviewer,
        payload={"decision": decision, "overridden_findings": overridden},
    )

    return RedirectResponse(
        url=f"/cases/{case_id}", status_code=status.HTTP_303_SEE_OTHER,
    )
