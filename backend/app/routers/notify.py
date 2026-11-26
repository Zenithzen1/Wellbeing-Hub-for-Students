"""/notifications, /notifications/{id}/read, /stream (SSE), /admin/announcements, /admin/dead-letters"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.deps import CurrentUser, get_db, require_role
from app.schemas import AnnouncementIn, AnnouncementOut, DeadLetterOut, NotificationOut
from app.services import notify

router = APIRouter(tags=["notify"])

KEEPALIVE_SECONDS = 15


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(limit: int = Query(50, ge=1, le=200),
                             user: CurrentUser = Depends(require_role("S", "C")), db: Session = Depends(get_db)):
    """Inbox: delivered messages and announcements, newest first."""
    return notify.inbox(db, notify.recipient_for(user), limit)


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_read(notification_id: int, user: CurrentUser = Depends(require_role("S", "C")),
                    db: Session = Depends(get_db)):
    try:
        notify.mark_read(db, notify.recipient_for(user), notification_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notification not found")
    return Response(status_code=204)


@router.get("/stream")
async def stream(user: CurrentUser = Depends(require_role("S", "C"))):
    """Server-Sent Events for this user: reminder, notification, offer, slot_taken."""
    channels = (notify.recipient_for(user), notify.BROADCAST)

    async def events():
        sub = notify.subscribe(channels)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event, data = await asyncio.wait_for(sub.queue.get(), timeout=KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield notify.format_sse(event, data)
        finally:
            notify.unsubscribe(sub)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/admin/announcements", response_model=AnnouncementOut, status_code=201)
async def announce(body: AnnouncementIn, _: CurrentUser = Depends(require_role("A")), db: Session = Depends(get_db)):
    """Announcement to everyone, now or at send_at (goes through the timed heap)."""
    row = notify.announce(db, body.title, body.body, body.send_at)
    return {"id": row.id, "title": body.title, "body": body.body, "send_at": row.send_at, "status": row.status}


@router.get("/admin/dead-letters", response_model=list[DeadLetterOut])
async def dead_letters(_: CurrentUser = Depends(require_role("A")), db: Session = Depends(get_db)):
    """Messages whose delivery failed 4 times."""
    return notify.dead_letters(db)
