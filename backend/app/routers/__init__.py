"""One router per URL group, mirroring services/. Routers only validate input, check the
caller's role and call one service method; no business logic here. Mounted under /api."""

from app.routers import analytics, auth, bookings, custodian, events, notify, recommend, waitlist

ALL_ROUTERS = [
    auth.router,
    bookings.router,
    waitlist.router,
    events.router,
    notify.router,
    recommend.router,
    analytics.router,
    custodian.router,
]
