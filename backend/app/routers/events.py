"""/events, /events/upcoming, /events/{id}/register"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app import clock
from app.deps import CurrentUser, get_current_user, get_db, require_role
from app.schemas import EventIn, EventOut, EventPatch, RegistrationOut
from app.services import events

router = APIRouter(tags=["events"])

DEFAULT_SPAN = timedelta(days=31)  # GET /events without `to`


def _out(db: Session, user: CurrentUser, recs: list) -> list[dict]:
    """Event dicts, plus the caller's own registration status when they are a student."""
    mine = None
    if user.role == "S" and user.pseudonym:
        mine = events.statuses_for(db, user.pseudonym, [rec.id for rec in recs])
    return [events.to_dict(rec, mine.get(rec.id) if mine is not None else None) for rec in recs]


@router.get("/events", response_model=list[EventOut])
async def list_events(
    from_: AwareDatetime | None = Query(None, alias="from", description="default: now"),
    to: AwareDatetime | None = Query(None, description="inclusive; default: from + 31 days"),
    tag: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Events starting between `from` and `to`, in start order (AVL range query)."""
    lo = from_ or clock.now()
    hi = to or lo + DEFAULT_SPAN
    try:
        recs = events.between(lo, hi, tag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _out(db, user, recs)


@router.get("/events/upcoming", response_model=list[EventOut])
async def upcoming_events(
    k: int = Query(5, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The next k events from now (AVL next_k)."""
    return _out(db, user, events.upcoming(k))


@router.post("/events", response_model=EventOut, status_code=201)
async def create_event(body: EventIn, _: CurrentUser = Depends(require_role("A")), db: Session = Depends(get_db)):
    try:
        rec = events.create(db, body.title, body.start, body.end, body.location, body.capacity, body.tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return events.to_dict(rec)


@router.patch("/events/{event_id}", response_model=EventOut)
async def update_event(event_id: int, body: EventPatch, _: CurrentUser = Depends(require_role("A")),
                       db: Session = Depends(get_db)):
    try:
        rec = events.update(db, event_id, **body.model_dump(exclude_unset=True))
    except events.EventNotFound:
        raise HTTPException(status_code=404, detail="Event not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return events.to_dict(rec)


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(event_id: int, _: CurrentUser = Depends(require_role("A")), db: Session = Depends(get_db)):
    try:
        events.remove(db, event_id)
    except events.EventNotFound:
        raise HTTPException(status_code=404, detail="Event not found")
    return Response(status_code=204)


@router.post("/events/{event_id}/register", response_model=RegistrationOut, status_code=201)
async def register(event_id: int, user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    """Register, or join the event's FIFO waitlist when it is full."""
    try:
        status = events.register(db, event_id, user.pseudonym)
    except events.EventNotFound:
        raise HTTPException(status_code=404, detail="Event not found")
    except events.RegistrationConflict as exc:
        raise HTTPException(status_code=409, detail=f"You are {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"event_id": event_id, "status": status}


@router.delete("/events/{event_id}/register", status_code=204)
async def unregister(event_id: int, user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    try:
        events.unregister(db, event_id, user.pseudonym)
    except events.EventNotFound:
        raise HTTPException(status_code=404, detail="Not registered for this event")
    return Response(status_code=204)
