"""/auth/register, /auth/login, /auth/logout, /me

The session is a JWT {sub, role, pse, exp} in an httpOnly, SameSite=Lax cookie (plan section 3.5).
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import auth
from app.config import settings
from app.deps import CurrentUser, get_current_user, get_db
from app.schemas import LoginIn, MeOut, RegisterIn
from app.services import identity

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=MeOut, status_code=201)
async def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Create a student account (argon2 password, HMAC pseudonym, sealed vault row). Log in afterwards."""
    try:
        acc = identity.register(db, body.email, body.password, body.name)
    except identity.EmailTaken:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    except auth.VaultNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return identity.me(db, acc.id, acc.role, auth.pseudonym_for(acc.email))


@router.post("/auth/login", response_model=MeOut)
async def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    try:
        acc, pse = identity.authenticate(db, body.email, body.password)
    except identity.BadCredentials:
        raise HTTPException(status_code=401, detail="Wrong email or password")
    response.set_cookie(auth.COOKIE, identity.token_for(acc, pse), max_age=int(settings.session_hours * 3600),
                        httponly=True, samesite="lax", secure=settings.cookie_secure, path="/")
    return identity.me(db, acc.id, acc.role, pse)


@router.post("/auth/logout", status_code=204)
async def logout():
    response = Response(status_code=204)
    response.delete_cookie(auth.COOKIE, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure)
    return response


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Who is logged in: role and display tag."""
    return identity.me(db, user.account_id, user.role, user.pseudonym)
