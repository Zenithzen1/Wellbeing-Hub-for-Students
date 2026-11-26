"""Business rules. Only services write to the database and update the structures
(write-through: DB commit first, then the in-memory structure)."""


def rebuild_all() -> None:
    """Rebuild every in-memory structure from SQLite on startup.

    Order (plan section 2): identity map, interval trees, events, waitlists, timed heap, graph.
    The timed heap is emptied first, so services can re-schedule their jobs (offer expiry,
    ageing) with notify.schedule_job() from their own rebuild().
    """
    from app.db import SessionLocal
    from app.services import events, notify

    notify.reset()
    db = SessionLocal()
    try:
        # TODO(Rithwik): identity map
        # TODO(Aditya): interval trees
        events.rebuild(db)
        # TODO(Aditya): waitlists (+ notify.schedule_job for open offers and the ageing check)
        notify.rebuild(db)
        # TODO(Rithwik): graph
    finally:
        db.close()
