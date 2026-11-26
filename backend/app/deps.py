"""FastAPI dependencies shared by the routers."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import SessionLocal


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass(frozen=True)
class CurrentUser:
    """Who is calling, from the JWT {sub, role, pse}. role is "S", "C", "A" or "K";
    pseudonym is set for students only."""

    account_id: int
    role: str
    pseudonym: str | None = None


def get_current_user(request: Request) -> CurrentUser:
    """Read and verify the JWT cookie; 401 if missing or invalid."""
    # TODO(Rithwik): decode the session cookie with auth.decode_token.
    raise NotImplementedError


def require_role(*roles: str) -> Callable[..., CurrentUser]:
    """Dependency: the current user, or 403 if their role is not one of `roles`."""

    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Not allowed for your role")
        return user

    return checker
