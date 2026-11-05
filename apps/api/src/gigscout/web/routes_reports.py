"""The connected pipeline and the owner report: every step from found to won, over time, with drill-downs."""

import csv
import io
from datetime import UTC, datetime, timedelta
from statistics import median

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from gigscout import analyst
from gigscout.platform import pipeline
from gigscout.platform.tables import AGENT_AUTHOR, LeadState, Outreach, Reply, Run
from gigscout.web.deps import PlatformDep, SessionDep, Ws, WsDep, audit
from gigscout.web.routes_leads import load_states

router = APIRouter(prefix="/api", tags=["reports"])

ALL_STEPS = (*pipeline.STAGES, *pipeline.EXITS)
DRILL_LIMIT = 200


def period(days: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(UTC)
    return end - timedelta(days=days), end


def workspace_steps(session, ws: Ws) -> list[pipeline.Step]:
    found = [(s.lead.id, s.seen_at) for s in ws.index.records()]
    return pipeline.with_found(pipeline.load_steps(session, ws.id), found)


@router.get("/pipeline")
def pipeline_overview(session: SessionDep, ws: WsDep, days: int = Query(default=30, ge=1, le=365)) -> dict:
    """Every step in one line for the period, plus the same steps per day for the charts."""
    start, end = period(days)
    steps = workspace_steps(session, ws)
    return {**pipeline.summary(steps, start, end), "days": days,
            "series": pipeline.series(steps, (end - timedelta(days=days - 1)).date(), days)}


@router.get("/pipeline/{stage}/leads")
def pipeline_leads(stage: str, session: SessionDep, ws: WsDep, days: int = Query(default=30, ge=1, le=365)) -> dict:
    """The leads behind one step: which ones reached it in the period, and when."""
    if stage not in ALL_STEPS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such pipeline step")
    start, end = period(days)
    hits = pipeline.leads_at(workspace_steps(session, ws), stage, start, end)[:DRILL_LIMIT]
    states = load_states(session, ws.id)
    items = []
    for hit in hits:
        lead = ws.index.get(hit.lead_id)
        if lead is None:
            continue
        state = states.get(hit.lead_id)
        items.append({"id": lead.id, "title": lead.title, "source": lead.source, "kind": lead.kind,
                      "client_name": lead.client.name if lead.client else None, "at": hit.at.isoformat(),
                      "status": state.status if state else "new", "score": state.score if state else None,
                      "deal_value_usd": state.deal_value_usd if state else None})
    return {"stage": stage, "label": pipeline.STAGE_LABELS[stage], "items": items}


@router.get("/reports/owner")
def owner_report(session: SessionDep, ws: WsDep, days: int = Query(default=30, ge=1, le=365)) -> dict:
    return build_owner_report(session, ws, days)


class AnalystQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    days: int = Field(default=30, ge=1, le=365)


@router.get("/analyst/insights")
def analyst_insights(session: SessionDep, ws: WsDep, days: int = Query(default=30, ge=1, le=365)) -> dict:
    """What moved in the period, computed from the report's numbers."""
    return {"insights": [i.model_dump() for i in analyst.insights(build_owner_report(session, ws, days))]}


@router.post("/analyst/ask")
async def analyst_ask(body: AnalystQuestion, platform: PlatformDep, session: SessionDep, ws: WsDep) -> dict:
    """A question about the pipeline, answered from its numbers only."""
    report = build_owner_report(session, ws, body.days)
    reply, by = await run_in_threadpool(analyst.answer, body.question, report, platform.service.deps.reasoner)
    audit(session, ws, "analyst.ask", "", question=body.question[:200])
    session.commit()
    return {**reply.model_dump(), "by": by, "days": body.days}


@router.get("/reports/owner.csv")
def owner_report_csv(session: SessionDep, ws: WsDep, days: int = Query(default=30, ge=1, le=365)) -> StreamingResponse:
    report = build_owner_report(session, ws, days)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Report", _safe(ws.name), report["start"], report["end"]])
    writer.writerow([])
    writer.writerow(["Step", "Leads", "Previous period", "Conversion", "Median hours", "Waiting now"])
    for s in report["stages"]:
        writer.writerow([s["label"], s["count"], s["previous"], s["conversion"] or "", s["median_hours"] or "",
                         s["waiting"]])
    writer.writerow([])
    writer.writerow(["Source", *ALL_STEPS, "Won value (USD)", "Reply rate"])
    for r in report["sources"]:
        writer.writerow([_safe(r["source"]), *(r[s] for s in ALL_STEPS), r["won_value"], r["reply_rate"] or ""])
    writer.writerow([])
    writer.writerow(["Person", *pipeline.STAGES[1:], *pipeline.EXITS, "Total"])
    for r in report["people"]:
        writer.writerow([_safe(r["actor"]), *(r[s] for s in (*pipeline.STAGES[1:], *pipeline.EXITS)), r["total"]])
    writer.writerow([])
    writer.writerow(["Won lead", "Source", "Value (USD)", "Won at"])
    for w in report["wins"]:
        writer.writerow([_safe(w["title"]), _safe(w["source"]), w["deal_value_usd"] or "", w["at"]])
    name = f"gigscout-report-{days}d-{report['end'][:10]}.csv"
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


def build_owner_report(session, ws: Ws, days: int, now: datetime | None = None) -> dict:
    """What came in, what went out, what was won, and which sources and people moved it, for one period."""
    start, end = period(days, now)
    records = ws.index.records()
    steps = pipeline.with_found(pipeline.load_steps(session, ws.id), [(s.lead.id, s.seen_at) for s in records])
    sources = {s.lead.id: s.lead.source for s in records}
    titles = {s.lead.id: s.lead.title for s in records}
    values = {lead_id: v for lead_id, v in session.execute(select(LeadState.lead_id, LeadState.deal_value_usd).where(
        LeadState.workspace_id == ws.id, LeadState.deal_value_usd.is_not(None)))}
    summary = pipeline.summary(steps, start, end)
    wins = pipeline.leads_at(steps, "won", start, end)
    previous_wins = pipeline.leads_at(steps, "won", start - (end - start), start)
    return {
        **summary, "days": days, "workspace": ws.name,
        "series": pipeline.series(steps, (end - timedelta(days=days - 1)).date(), days),
        "revenue": {"won": round(sum(values.get(w.lead_id, 0.0) for w in wins), 2),
                    "previous": round(sum(values.get(w.lead_id, 0.0) for w in previous_wins), 2),
                    "deals": len(wins), "valued": sum(1 for w in wins if w.lead_id in values)},
        "wins": [{"id": w.lead_id, "title": titles.get(w.lead_id, w.lead_id), "source": sources.get(w.lead_id, ""),
                  "deal_value_usd": values.get(w.lead_id), "at": w.at.isoformat()} for w in wins[:50]],
        "sources": pipeline.by_source(steps, sources, values, start, end),
        "people": pipeline.by_person(steps, start, end),
        "pitches": _pitch_stats(session, ws.id, start, end),
        "runs": _run_stats(session, ws.id, start, end),
        "replies": dict(session.execute(select(Reply.intent, func.count()).where(
            Reply.workspace_id == ws.id, Reply.received_at >= start, Reply.received_at < end)
            .group_by(Reply.intent)).all()),
    }


def _pitch_stats(session, workspace_id: int, start: datetime, end: datetime) -> dict:
    rows = list(session.scalars(select(Outreach).where(
        Outreach.workspace_id == workspace_id, Outreach.created_at >= start, Outreach.created_at < end)))
    reviewed = [r for r in rows if r.status != "draft"]
    approved = [r for r in reviewed if r.status != "rejected"]
    waits = [(_aware(r.reviewed_at) - _aware(r.created_at)).total_seconds() / 3600
             for r in reviewed if r.reviewed_at]
    return {
        "drafted": len(rows), "by_agents": sum(r.created_by == AGENT_AUTHOR for r in rows),
        "approved": len(approved), "rejected": len(reviewed) - len(approved),
        "waiting": len(rows) - len(reviewed), "replied": sum(r.status == "replied" for r in rows),
        "approval_rate": round(len(approved) / len(reviewed), 3) if reviewed else None,
        "median_review_hours": round(median(waits), 1) if waits else None,
    }


def _run_stats(session, workspace_id: int, start: datetime, end: datetime) -> dict:
    runs = list(session.scalars(select(Run).where(
        Run.workspace_id == workspace_id, Run.created_at >= start, Run.created_at < end)))
    return {"total": len(runs), "succeeded": sum(r.status == "succeeded" for r in runs),
            "failed": sum(r.status == "failed" for r in runs),
            "leads_fetched": sum(r.fetched_count or 0 for r in runs), "new_leads": sum(r.new_count or 0 for r in runs)}


def _safe(value: str) -> str:
    """Stop spreadsheet apps from running a cell as a formula (CSV injection)."""
    return f"'{value}" if value.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@") or value[:1] in ("\t", "\r") else value


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
