"""/auth/register, /auth/login, /auth/logout, /me"""

from fastapi import APIRouter

router = APIRouter(tags=["auth"])
