"""Operations: agency profiles, agent runs and schedules."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from gigscout.models import AgencyProfile
from gigscout.platform.runs import ProfileNotFound
from gigscout.platform.scheduler import InvalidCron
from gigscout.platform.tables import AgencyProfileRecord, Run, Schedule
from gigscout.profile_templates import TEMPLATES, closest_template
from gigscout.web.deps import AdminDep, PlatformDep, SessionDep, UserDep, WriterDep, WsDep, audit
from gigscout.web.schemas import (
    CronPreview,
    ProfileOut,
    ProfileSuggestOut,
    ProfileSuggestRequest,
    RunCreate,
    RunDetail,
    RunOut,
    ScheduleIn,
    ScheduleOut,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["operations"])


# --- agency profiles --------------------------------------------------------------------------------------------
@router.get("/profiles")
def list_profiles(session: SessionDep, ws: WsDep) -> list[ProfileOut]:
    records = session.scalars(select(AgencyProfileRecord).where(AgencyProfileRecord.workspace_id == ws.id)
                              .order_by(AgencyProfileRecord.id))
    return [ProfileOut.model_validate(p) for p in records]


@router.get("/profiles/templates")
def profile_templates(_: UserDep) -> list[dict]:
    """Starting points for common kinds of company (software, marketing, legal, construction, ...)."""
    return [asdict(t) for t in TEMPLATES]


@router.post("/profiles/suggest")
def suggest_profile(body: ProfileSuggestRequest, platform: PlatformDep, _: AdminDep) -> ProfileSuggestOut:
    """Fill a profile from one sentence: the LLM when available, else the closest template, else nothing."""
    reasoner = platform.service.deps.reasoner
    if reasoner is not None:
        try:
            s = reasoner.suggest_profile(body.company_type, body.description)
            return ProfileSuggestOut(source="ai", **s.model_dump())
        except Exception:
            log.warning("Profile suggestion failed; falling back to templates", exc_info=True)
    template = closest_template(body.company_type)
    if template is None:
        return ProfileSuggestOut(source="none", services=[], skills=[], keywords=[], exclude=[], industries=[])
    return ProfileSuggestOut(
        source="template", services=list(template.services), skills=list(template.skills),
        keywords=list(template.keywords), exclude=list(template.exclude), industries=[],
    )


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def create_profile(body: AgencyProfile, session: SessionDep, admin: AdminDep) -> ProfileOut:
    record = AgencyProfileRecord(workspace_id=admin.id, name=body.name, data=body.model_dump(mode="json"))
    session.add(record)
    session.flush()
    audit(session, admin, "profile.create", str(record.id), name=body.name)
    session.commit()
    return ProfileOut.model_validate(record)


@router.put("/profiles/{profile_id}")
def update_profile(profile_id: int, body: AgencyProfile, session: SessionDep, admin: AdminDep) -> ProfileOut:
    record = _profile(session, admin.id, profile_id)
    record.name, record.data = body.name, body.model_dump(mode="json")
    audit(session, admin, "profile.update", str(profile_id), name=body.name)
    session.commit()
    return ProfileOut.model_validate(record)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int, platform: PlatformDep, session: SessionDep, admin: AdminDep) -> None:
    record = _profile(session, admin.id, profile_id)
    for schedule in session.scalars(select(Schedule).where(Schedule.profile_id == profile_id)):
        platform.schedules.remove(schedule.id)
    audit(session, admin, "profile.delete", str(profile_id), name=record.name)
    session.delete(record)
    session.commit()


# --- runs -------------------------------------------------------------------------------------------------------
@router.get("/runs")
def list_runs(
    session: SessionDep, ws: WsDep, limit: int = Query(default=50, ge=1, le=500), status_: str | None = Query(
        default=None, alias="status"),
) -> list[RunOut]:
    stmt = select(Run).where(Run.workspace_id == ws.id).order_by(Run.created_at.desc()).limit(limit)
    if status_:
        stmt = stmt.where(Run.status == status_)
    return [RunOut.model_validate(r) for r in session.scalars(stmt)]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
def start_run(body: RunCreate, platform: PlatformDep, session: SessionDep, ws: WriterDep) -> RunOut:
    if reason := platform.billing.run_blocked(ws.id):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, reason)
    try:
        run = platform.runs.submit(ws.id, body.profile_id, body.mode, "manual", ws.email)
    except ProfileNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    audit(session, ws, "run.start", run.id, profile_id=body.profile_id, mode=body.mode)
    session.commit()
    return RunOut.model_validate(run)


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: SessionDep, ws: WsDep) -> RunDetail:
    run = session.get(Run, run_id)
    if run is None or run.workspace_id != ws.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return RunDetail.model_validate(run)


@router.get("/runs/{run_id}/activity")
def run_activity(run_id: str, platform: PlatformDep, ws: WsDep) -> list[dict]:
    """Structured activity for the cockpit: live while the run is going, stored once it has finished."""
    activity = platform.runs.activity(run_id, ws.id)
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return activity


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, platform: PlatformDep, session: SessionDep, ws: WriterDep) -> dict:
    """Cancel a queued run, or ask a running one to stop at its next step."""
    run = session.get(Run, run_id)
    if run is None or run.workspace_id != ws.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    outcome = platform.runs.cancel(run_id)
    if outcome is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This run has already finished")
    audit(session, ws, "run.cancel" if outcome == "cancelled" else "run.stop", run_id)
    session.commit()
    return {"status": outcome}


# --- schedules --------------------------------------------------------------------------------------------------
@router.get("/schedules")
def list_schedules(platform: PlatformDep, session: SessionDep, ws: WsDep) -> list[ScheduleOut]:
    rows = session.scalars(select(Schedule).where(Schedule.workspace_id == ws.id).order_by(Schedule.id))
    return [_schedule_out(platform, s) for s in rows]


@router.get("/schedules/preview")
def preview_cron(platform: PlatformDep, _: UserDep, cron: str = Query(min_length=1, max_length=120)) -> CronPreview:
    try:
        return CronPreview(cron=cron, valid=True, next_runs=platform.schedules.upcoming(cron))
    except InvalidCron as exc:
        return CronPreview(cron=cron, valid=False, error=str(exc))


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
def create_schedule(body: ScheduleIn, platform: PlatformDep, session: SessionDep, admin: AdminDep) -> ScheduleOut:
    _profile(session, admin.id, body.profile_id)
    _validate_cron(platform, body.cron)
    schedule = Schedule(**body.model_dump(), workspace_id=admin.id, created_by=admin.email)
    session.add(schedule)
    session.flush()
    audit(session, admin, "schedule.create", str(schedule.id), **body.model_dump())
    session.commit()
    platform.schedules.sync(schedule)
    return _schedule_out(platform, schedule)


@router.put("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int, body: ScheduleIn, platform: PlatformDep, session: SessionDep, admin: AdminDep,
) -> ScheduleOut:
    schedule = _schedule(session, admin.id, schedule_id)
    _profile(session, admin.id, body.profile_id)
    _validate_cron(platform, body.cron)
    for field, value in body.model_dump().items():
        setattr(schedule, field, value)
    audit(session, admin, "schedule.update", str(schedule_id), **body.model_dump())
    session.commit()
    platform.schedules.sync(schedule)
    return _schedule_out(platform, schedule)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, platform: PlatformDep, session: SessionDep, admin: AdminDep) -> None:
    schedule = _schedule(session, admin.id, schedule_id)
    platform.schedules.remove(schedule_id)
    audit(session, admin, "schedule.delete", str(schedule_id), name=schedule.name)
    session.delete(schedule)
    session.commit()


@router.post("/schedules/{schedule_id}/trigger")
def trigger_schedule(schedule_id: int, platform: PlatformDep, session: SessionDep, ws: WriterDep) -> dict:
    _schedule(session, ws.id, schedule_id)
    if reason := platform.billing.run_blocked(ws.id):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, reason)
    run_id = platform.schedules.fire(schedule_id)
    if run_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A run for this profile is already queued or running")
    audit(session, ws, "schedule.trigger", str(schedule_id), run_id=run_id)
    session.commit()
    return {"run_id": run_id}


def _profile(session, workspace_id: int, profile_id: int) -> AgencyProfileRecord:
    record = session.get(AgencyProfileRecord, profile_id)
    if record is None or record.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agency profile not found")
    return record


def _schedule(session, workspace_id: int, schedule_id: int) -> Schedule:
    schedule = session.get(Schedule, schedule_id)
    if schedule is None or schedule.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return schedule


def _validate_cron(platform, cron: str) -> None:
    try:
        platform.schedules.upcoming(cron, count=1)
    except InvalidCron as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _schedule_out(platform, schedule: Schedule) -> ScheduleOut:
    out = ScheduleOut.model_validate(schedule)
    return out.model_copy(update={"next_run_at": platform.schedules.next_run(schedule.id)})
