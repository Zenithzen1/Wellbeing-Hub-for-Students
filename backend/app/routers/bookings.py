"""/counsellors, /counsellors/{id}/free, /counsellor/availability, /bookings, /counsellor/sessions

SSE events sent on the "all" channel when a grid changes: slot_taken, slot_freed {counsellor_id, start, end}.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app import clock
from app.deps import CurrentUser, get_current_user, get_db, require_role
from app.schemas import (
    AvailabilityIn,
    AvailabilityOut,
    BookingIn,
    BookingOut,
    BookingPatch,
    CounsellorOut,
    FreeDayOut,
    SessionOut,
)
from app.services import booking

router = APIRouter(tags=["bookings"])


def _my_counsellor_id(user: CurrentUser) -> int:
    try:
        return booking.counsellor_for_account(user.account_id).id
    except booking.CounsellorNotFound:
        raise HTTPException(status_code=403, detail="This account has no counsellor profile")


def _today() -> date:
    return clock.to_local(clock.now()).date()


# --- students: browse and book --------------------------------------------------------------------

@router.get("/counsellors", response_model=list[CounsellorOut])
async def list_counsellors(_: CurrentUser = Depends(get_current_user)):
    return [booking.to_counsellor_dict(rec) for rec in booking.counsellors()]


@router.get("/counsellors/{counsellor_id}/free", response_model=list[FreeDayOut])
async def free_time(
    counsellor_id: int,
    day: date | None = Query(None, alias="date", description="Dubai-time date; default today"),
    days: int = Query(1, ge=1, le=7, description="how many days from `date`"),
    first_visit: bool = False,
    _: CurrentUser = Depends(get_current_user),
):
    """The booking grid: open windows, busy time and free start times (interval tree + gap sweep)."""
    first = day or _today()
    try:
        return [booking.free_day(counsellor_id, first + timedelta(days=i), first_visit) for i in range(days)]
    except booking.CounsellorNotFound:
        raise HTTPException(status_code=404, detail="Counsellor not found")


@router.post("/bookings", response_model=BookingOut, status_code=201)
async def create_booking(body: BookingIn, user: CurrentUser = Depends(require_role("S")),
                         db: Session = Depends(get_db)):
    # TODO(Rithwik): when body.reveal is ticked, pass identity_blob = the student's name and email
    # encrypted with the server key (identity service).
    try:
        row = booking.book(db, user.pseudonym, body.counsellor_id, body.start, body.reason, body.first_visit,
                           body.reveal, identity_blob=None)
    except booking.CounsellorNotFound:
        raise HTTPException(status_code=404, detail="Counsellor not found")
    except booking.SlotTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return booking.to_dict(row)


@router.get("/bookings/me", response_model=list[BookingOut])
async def my_bookings(user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    return [booking.to_dict(row) for row in booking.my_bookings(db, user.pseudonym)]


@router.delete("/bookings/{booking_id}", status_code=204)
async def cancel_booking(booking_id: int, user: CurrentUser = Depends(require_role("S", "C")),
                         db: Session = Depends(get_db)):
    """Cancel (student: own booking; counsellor: a session with them). The time goes to the waitlist first."""
    try:
        if user.role == "S":
            booking.cancel(db, booking_id, pseudonym=user.pseudonym)
        else:
            booking.cancel(db, booking_id, counsellor_id=_my_counsellor_id(user))
    except booking.BookingNotFound:
        raise HTTPException(status_code=404, detail="Booking not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(status_code=204)


# --- counsellors: availability and sessions ---------------------------------------------------------

@router.get("/counsellor/availability", response_model=list[AvailabilityOut])
async def my_availability(
    from_: AwareDatetime | None = Query(None, alias="from", description="default: now"),
    to: AwareDatetime | None = Query(None, description="default: from + 14 days"),
    user: CurrentUser = Depends(require_role("C")),
    db: Session = Depends(get_db),
):
    lo = from_ or clock.now()
    hi = to or lo + timedelta(days=14)
    try:
        rows = booking.list_availability(db, _my_counsellor_id(user), lo, hi)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [booking.to_availability_dict(row) for row in rows]


@router.post("/counsellor/availability", response_model=AvailabilityOut, status_code=201)
async def add_availability(body: AvailabilityIn, user: CurrentUser = Depends(require_role("C")),
                           db: Session = Depends(get_db)):
    """Publish an open window or block time (interval tree overlap check)."""
    try:
        row = booking.add_availability(db, _my_counsellor_id(user), body.start, body.end, body.kind, body.note)
    except booking.SlotTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return booking.to_availability_dict(row)


@router.delete("/counsellor/availability/{availability_id}", status_code=204)
async def remove_availability(availability_id: int, user: CurrentUser = Depends(require_role("C")),
                              db: Session = Depends(get_db)):
    try:
        booking.remove_availability(db, _my_counsellor_id(user), availability_id)
    except booking.AvailabilityNotFound:
        raise HTTPException(status_code=404, detail="Availability not found")
    except booking.SlotTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return Response(status_code=204)


@router.get("/counsellor/sessions", response_model=list[SessionOut])
async def my_sessions(day: date | None = Query(None, alias="date", description="Dubai-time date; default today"),
                      user: CurrentUser = Depends(require_role("C")), db: Session = Depends(get_db)):
    """Sessions that day: pseudonym tag and reason; a name only where the student opted in."""
    # TODO(Rithwik): decrypt row.enc_identity for revealed bookings and pass it as identity=.
    rows = booking.sessions_on(db, _my_counsellor_id(user), day or _today())
    return [booking.to_session_dict(row) for row in rows]


@router.patch("/bookings/{booking_id}", response_model=SessionOut)
async def mark_booking(booking_id: int, body: BookingPatch, user: CurrentUser = Depends(require_role("C")),
                       db: Session = Depends(get_db)):
    """Mark a session that has started as completed or no_show."""
    try:
        row = booking.mark(db, _my_counsellor_id(user), booking_id, body.status)
    except booking.BookingNotFound:
        raise HTTPException(status_code=404, detail="Booking not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return booking.to_session_dict(row)
