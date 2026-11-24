"""Creates the FastAPI app.

Startup order (plan section 2):
  1. create any missing SQLite tables,
  2. rebuild every in-memory data structure from the database,
  3. start the 15-second scheduler tick.

Run from backend/ with exactly ONE worker (each process would get its own heaps and trees):
    uvicorn app.main:app --reload
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import scheduler
from app.config import settings
from app.db import init_db
from app.routers import ALL_ROUTERS
from app.services import rebuild_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    rebuild_all()
    task = asyncio.create_task(scheduler.run(settings.scheduler_interval_seconds))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

for router in ALL_ROUTERS:
    app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Liveness check: the app is up and the routers are mounted."""
    return {"status": "ok"}


# Production build: FastAPI serves the React app too (one process, one URL).
# In development Vite runs on :5173 and proxies /api to :8000, so this is skipped.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
