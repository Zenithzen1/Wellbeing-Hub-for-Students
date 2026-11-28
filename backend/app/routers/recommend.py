"""/resources, /tags, /me/interests, /engagements, /recommendations"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.deps import CurrentUser, get_current_user, get_db, require_role
from app.schemas import EngagementIn, InterestsIn, RecommendationsOut, ResourceIn, ResourceOut
from app.services import recommend

router = APIRouter(tags=["recommend"])


@router.get("/resources", response_model=list[ResourceOut])
async def list_resources(tag: str | None = None, user: CurrentUser = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Articles, audio and videos, newest first; students also see their own saved/finished marks."""
    mine = recommend.my_engagements(db, user.pseudonym) if user.role == "S" and user.pseudonym else None
    return [recommend.resource_dict(rec, mine.get(f"r:{rec.id}") if mine is not None else None)
            for rec in recommend.resources(tag)]


@router.post("/resources", response_model=ResourceOut, status_code=201)
async def create_resource(body: ResourceIn, _: CurrentUser = Depends(require_role("A")), db: Session = Depends(get_db)):
    try:
        rec = recommend.create_resource(db, body.title, body.kind, body.url, body.tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return recommend.resource_dict(rec)


@router.get("/tags", response_model=list[str])
async def list_tags(_: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """The curated interest tags."""
    return recommend.tags(db)


@router.get("/me/interests", response_model=list[str])
async def my_interests(user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    return recommend.interests(db, user.pseudonym)


@router.put("/me/interests", response_model=list[str])
async def set_interests(body: InterestsIn, user: CurrentUser = Depends(require_role("S")),
                        db: Session = Depends(get_db)):
    """Replace my interest tags (graph edges student - tag)."""
    try:
        return recommend.set_interests(db, user.pseudonym, body.tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/engagements", status_code=201)
async def engage(body: EngagementIn, user: CurrentUser = Depends(require_role("S")), db: Session = Depends(get_db)):
    """I attended, saved or finished an item (graph edge student - item). 200 if already recorded."""
    try:
        new = recommend.engage(db, user.pseudonym, body.item, body.kind)
    except recommend.ItemNotFound:
        raise HTTPException(status_code=404, detail="Item not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(status_code=201 if new else 200)


@router.get("/recommendations", response_model=RecommendationsOut)
async def recommendations(k: int = Query(5, ge=1, le=recommend.MAX_K), user: CurrentUser = Depends(require_role("S")),
                          db: Session = Depends(get_db)):
    """Top k items for me: 2-hop tag matches plus the 3-hop similar-students term (support >= 3)."""
    return recommend.recommend(db, user.pseudonym, k)
