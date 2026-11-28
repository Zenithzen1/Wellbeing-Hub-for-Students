"""/waitlist, /offers/{id}/accept | decline, /counsellor/waitlist

A new offer is pushed to the student's tabs as an SSE "offer" event (and lands in their inbox).
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.deps import CurrentUser, get_db, require_role
from app.schemas import BookingOut, OfferAcceptIn, WaitlistCountsOut, WaitlistIn, WaitlistOut
from app.services import booking, identity, waitlist

router = APIRouter(tags=["waitlist"])


@router.post("/waitlist", response_model=WaitlistOut, status_code=201)
async def join(body: WaitlistIn, user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    """Join a counsellor's line (or the "any counsellor" line) when there is no free time in the next 7 days."""
    try:
        rec = waitlist.join(db, user.pseudonym, body.counsellor_id, body.urgent)
    except booking.CounsellorNotFound:
        raise HTTPException(status_code=404, detail="Counsellor not found")
    except waitlist.WaitlistConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return next(e for e in waitlist.my_entries(db, user.pseudonym) if e["id"] == rec.id)


@router.get("/waitlist", response_model=list[WaitlistOut])
async def my_waitlists(user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    """My lines, my place in each, and any open offer (so a reloaded page can show the offer again)."""
    return waitlist.my_entries(db, user.pseudonym)


@router.delete("/waitlist/{entry_id}", status_code=204)
async def leave(entry_id: int, user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    try:
        waitlist.leave(db, user.pseudonym, entry_id)
    except waitlist.EntryNotFound:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    return Response(status_code=204)


@router.post("/offers/{offer_id}/accept", response_model=BookingOut, status_code=201)
async def accept(offer_id: int, body: OfferAcceptIn | None = Body(None),
                 user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    """Book the offered time. You leave all your other waitlists."""
    body = body or OfferAcceptIn()
    try:
        blob = identity.identity_blob(db, user.account_id) if body.reveal else None
        row = waitlist.accept(db, user.pseudonym, offer_id, body.reason, body.reveal, identity_blob=blob)
    except waitlist.OfferNotFound:
        raise HTTPException(status_code=404, detail="Offer not found")
    except (waitlist.OfferGone, booking.SlotTaken) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return booking.to_dict(row)


@router.post("/offers/{offer_id}/decline", status_code=204)
async def decline(offer_id: int, user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    """Say no: you leave that waitlist and the time goes to the next person."""
    try:
        waitlist.decline(db, user.pseudonym, offer_id)
    except waitlist.OfferNotFound:
        raise HTTPException(status_code=404, detail="Offer not found")
    except waitlist.OfferGone as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return Response(status_code=204)


@router.get("/counsellor/waitlist", response_model=WaitlistCountsOut)
async def counsellor_counts(user: CurrentUser = Depends(require_role("C"))):
    """How many students are waiting for me (and for anyone), without saying who."""
    try:
        cid = booking.counsellor_for_account(user.account_id).id
    except booking.CounsellorNotFound:
        raise HTTPException(status_code=403, detail="This account has no counsellor profile")
    return waitlist.counts(cid)
