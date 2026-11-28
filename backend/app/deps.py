"""FastAPI dependencies shared by the routers."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import auth
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
    """Read and verify the JWT cookie (or an "Authorization: Bearer" header, for scripts); 401 if
    missing or invalid. Student routes take the pseudonym from here, never from the database."""
    token = request.cookies.get(auth.COOKIE)
    if not token:
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        token = value.strip() if scheme.lower() == "bearer" else None
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        claims = auth.decode_token(token)
    except auth.InvalidToken:
        raise HTTPException(status_code=401, detail="Session expired or invalid; please log in again")
    return CurrentUser(int(claims["sub"]), claims["role"], claims.get("pse"))


def require_role(*roles: str) -> Callable[..., CurrentUser]:
    """Dependency: the current user, or 403 if their role is not one of `roles`."""

    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Not allowed for your role")
        return user

    return checker
