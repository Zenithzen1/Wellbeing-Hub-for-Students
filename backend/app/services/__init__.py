"""Business rules. Only services write to the database and update the structures
(write-through: DB commit first, then the in-memory structure)."""


def rebuild_all() -> None:
    """Rebuild every in-memory structure from SQLite on startup.

    Order (plan section 2): identity map, interval trees, events, waitlists, timed heap, graph.
    The timed heap is emptied first, so services can re-schedule their jobs (offer expiry,
    ageing) with notify.schedule_job() from their own rebuild().
    """
    from app.db import SessionLocal
    from app.services import booking, events, notify, waitlist

    notify.reset()
    db = SessionLocal()
    try:
        # TODO(Rithwik): identity map
        booking.rebuild(db)   # interval trees (sessions, blocked time, open-offer holds)
        events.rebuild(db)
        waitlist.rebuild(db)  # heaps + offer-expiry and ageing jobs
        notify.rebuild(db)
        # TODO(Rithwik): graph
    finally:
        db.close()
