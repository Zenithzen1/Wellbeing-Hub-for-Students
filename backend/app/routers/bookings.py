"""/counsellors, /counsellors/{id}/free, /counsellor/availability, /bookings, /counsellor/sessions"""

from fastapi import APIRouter

router = APIRouter(tags=["bookings"])
