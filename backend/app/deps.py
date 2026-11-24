"""FastAPI dependencies shared by the routers."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db import SessionLocal


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# TODO(Rithwik): get_current_user (reads the JWT cookie) and require_role("S" | "C" | "A" | "K").
