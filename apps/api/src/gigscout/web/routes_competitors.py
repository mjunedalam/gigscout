"""Competitor watch: the companies a workspace competes with, and the public contracts they won."""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from gigscout.platform.tables import Competitor, CompetitorWin
from gigscout.web.deps import AdminDep, PlatformDep, SessionDep, WriterDep, WsDep, audit
from gigscout.web.schemas import UtcDatetime

router = APIRouter(prefix="/api/competitors", tags=["insights"])


class CompetitorIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CompetitorOut(BaseModel):
    id: int
    name: str
    wins: int
    last_win_at: UtcDatetime | None


class WinOut(BaseModel):
    id: int
    competitor: str
    supplier: str
    title: str
    buyer: str
    amount: float | None
    currency: str | None
    awarded_at: UtcDatetime | None
    url: str


@router.get("")
def list_competitors(session: SessionDep, ws: WsDep) -> list[CompetitorOut]:
    rows = session.execute(
        select(Competitor, func.count(CompetitorWin.id), func.max(CompetitorWin.awarded_at))
        .outerjoin(CompetitorWin, CompetitorWin.competitor_id == Competitor.id)
        .where(Competitor.workspace_id == ws.id).group_by(Competitor.id).order_by(Competitor.name))
    return [CompetitorOut(id=c.id, name=c.name, wins=n, last_win_at=last) for c, n, last in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_competitor(body: CompetitorIn, session: SessionDep, ws: AdminDep) -> CompetitorOut:
    name = " ".join(body.name.split())
    if session.scalar(select(Competitor.id).where(Competitor.workspace_id == ws.id, Competitor.name == name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Already watched")
    competitor = Competitor(workspace_id=ws.id, name=name, created_by=ws.email)
    session.add(competitor)
    session.flush()
    audit(session, ws, "competitor.add", name)
    session.commit()
    return CompetitorOut(id=competitor.id, name=name, wins=0, last_win_at=None)


@router.delete("/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_competitor(competitor_id: int, session: SessionDep, ws: AdminDep) -> None:
    competitor = session.get(Competitor, competitor_id)
    if competitor is None or competitor.workspace_id != ws.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not watched")
    audit(session, ws, "competitor.remove", competitor.name)
    session.delete(competitor)
    session.commit()


@router.get("/wins")
def list_wins(session: SessionDep, ws: WsDep, limit: int = Query(default=100, ge=1, le=500)) -> list[WinOut]:
    rows = session.execute(
        select(CompetitorWin, Competitor.name).join(Competitor, Competitor.id == CompetitorWin.competitor_id)
        .where(CompetitorWin.workspace_id == ws.id)
        .order_by(CompetitorWin.awarded_at.desc().nulls_last(), CompetitorWin.id.desc()).limit(limit))
    return [WinOut(id=w.id, competitor=name, supplier=w.supplier, title=w.title, buyer=w.buyer, amount=w.amount,
                   currency=w.currency, awarded_at=w.awarded_at, url=w.url) for w, name in rows]


@router.post("/check")
def check_now(platform: PlatformDep, ws: WriterDep) -> dict:
    """Read the latest award notices now (they are shared and refreshed at most every few hours)."""
    try:
        return platform.competitors.check(ws.id)
    except Exception as exc:
        reason = f"Could not read award notices ({type(exc).__name__})"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, reason) from exc
