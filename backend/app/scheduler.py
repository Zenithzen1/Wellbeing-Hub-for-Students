"""Background loop started with the app (plan sections 2 and 7).

Every tick it pops due items from the timed heap: reminders and announcements go to the
delivery queue; expired waitlist offers and ageing jobs are handled directly.
"""

import asyncio
import logging

from app.db import SessionLocal
from app.services import notify

log = logging.getLogger(__name__)


async def tick() -> None:
    """One pass: handle everything whose send_at <= clock.now().

    Pops due entries from the timed heap: messages go to the FIFO delivery queue and are delivered;
    internal jobs (offer expiry, ageing) run through the handlers their services registered with
    notify.register_job(). Runs on the event loop thread, like the async routes.
    """
    db = SessionLocal()
    try:
        notify.tick(db)
    finally:
        db.close()


async def run(interval_seconds: float) -> None:
    while True:
        try:
            await tick()
        except Exception:  # one bad job must not kill the loop
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval_seconds)
