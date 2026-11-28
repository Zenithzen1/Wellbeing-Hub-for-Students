"""/custodian/reveal, /audit"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import auth
from app.deps import CurrentUser, get_db, require_role
from app.schemas import AuditOut, RevealIn, RevealOut
from app.services import identity

router = APIRouter(tags=["custodian"])


@router.post("/custodian/reveal", response_model=RevealOut)
async def reveal(body: RevealIn, user: CurrentUser = Depends(require_role("K")), db: Session = Depends(get_db)):
    """Break-glass: the reason goes into the audit log first, then one vault row is unsealed with the
    private key supplied here (never stored). The result is shown once."""
    try:
        return identity.break_glass(db, user.account_id, body.target, body.reason, body.private_key)
    except identity.PseudonymNotFound:
        raise HTTPException(status_code=404, detail="No student with that pseudonym")
    except identity.AmbiguousTag as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except auth.BadKey as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/audit", response_model=list[AuditOut])
async def audit(limit: int = Query(200, ge=1, le=1000), _: CurrentUser = Depends(require_role("A", "K")),
                db: Session = Depends(get_db)):
    """The append-only audit log, newest first. Every reveal is visible to the department."""
    return identity.audit_log(db, limit)
