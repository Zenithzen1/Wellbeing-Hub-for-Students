"""Business rules. Only services write to the database and update the structures
(write-through: DB commit first, then the in-memory structure)."""


def rebuild_all() -> None:
    """Rebuild every in-memory structure from SQLite on startup.

    Order (plan section 2): identity map, interval trees, events, waitlists, timed heap, graph.
    """
    # TODO: call each service's rebuild() once they exist.
