"""/notifications, /notifications/{id}/read, /stream (SSE), /admin/announcements"""

from fastapi import APIRouter

router = APIRouter(tags=["notify"])
