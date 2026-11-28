"""/analytics/summary, /analytics/export.csv"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.deps import CurrentUser, get_db, require_role
from app.schemas import AnalyticsOut
from app.services import analytics

router = APIRouter(tags=["analytics"])


def _summary(db: Session, first: date | None, last: date | None) -> dict:
    try:
        return analytics.summary(db, first, last)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/analytics/summary", response_model=AnalyticsOut)
async def summary(
    first: date | None = Query(None, alias="from", description="Dubai date, moved to its Monday; default 8 weeks ago"),
    last: date | None = Query(None, alias="to", description="Dubai date, moved to its Sunday; default today"),
    _: CurrentUser = Depends(require_role("A")),
    db: Session = Depends(get_db),
):
    """Department trends, counts only, with k = 5 and complementary suppression."""
    return _summary(db, first, last)


@router.get("/analytics/export.csv")
async def export_csv(
    first: date | None = Query(None, alias="from"),
    last: date | None = Query(None, alias="to"),
    _: CurrentUser = Depends(require_role("A")),
    db: Session = Depends(get_db),
):
    """Exactly what the dashboard shows, after suppression. No pseudonyms, no row-level data."""
    data = _summary(db, first, last)
    name = f"wellbeing-analytics-{data['first_day']}-to-{data['last_day']}.csv"
    return Response(analytics.to_csv(data), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
