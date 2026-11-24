"""Background loop started with the app (plan sections 2 and 7).

Every tick it pops due items from the timed heap: reminders and announcements go to the
delivery queue; expired waitlist offers and ageing jobs are handled directly.
"""

import asyncio
import logging

log = logging.getLogger(__name__)


async def tick() -> None:
    """One pass: handle everything whose send_at <= clock.now(). Filled in by the notify service."""
    # TODO(Divyam): pop timed heap while due -> FIFO delivery queue; expire offers (Aditya).


async def run(interval_seconds: float) -> None:
    while True:
        try:
            await tick()
        except Exception:  # one bad job must not kill the loop
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval_seconds)
