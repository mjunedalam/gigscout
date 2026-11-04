"""Workspaces: the companies a person works in, switching between them, and creating new ones."""

import secrets

from fastapi import APIRouter, status
from sqlalchemy import func, select

from gigscout.platform.tables import (
    AgencyProfileRecord,
    Connector,
    DigestSettings,
    LeadState,
    Membership,
    Run,
    SourceToggle,
    User,
    Workspace,
)
from gigscout.web.deps import AdminDep, PlatformAdminDep, SessionDep, WsDep, audit
from gigscout.web.schemas import SetupStep, WorkspaceCreate, WorkspaceDetail, WorkspaceOut

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def workspaces_of(session, user: User) -> list[WorkspaceOut]:
    """Where this person can work. Platform admins see every workspace (as owner where they are not a member)."""
    mine = {m.workspace_id: m.role for m in session.scalars(select(Membership).where(Membership.user_id == user.id))}
    stmt = select(Workspace).order_by(Workspace.id)
    if user.role != "admin":
        stmt = stmt.where(Workspace.id.in_(mine or [-1]))
    return [WorkspaceOut(id=w.id, name=w.name, role=mine.get(w.id, "owner")) for w in session.scalars(stmt)]


@router.get("")
def list_workspaces(session: SessionDep, ws: WsDep) -> list[WorkspaceOut]:
    return workspaces_of(session, ws.user)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, session: SessionDep, admin: PlatformAdminDep) -> WorkspaceOut:
    """A new, empty workspace; whoever creates it is its first owner."""
    workspace = Workspace(name=body.name.strip(), form_key=secrets.token_urlsafe(24))
    session.add(workspace)
    session.flush()
    session.add(Membership(user_id=admin.id, workspace_id=workspace.id, role="owner"))
    audit(session, admin, "workspace.create", str(workspace.id), workspace_id=workspace.id, name=workspace.name)
    session.commit()
    return WorkspaceOut(id=workspace.id, name=workspace.name, role="owner")


@router.get("/current")
def current(session: SessionDep, ws: WsDep) -> WorkspaceDetail:
    workspace = session.get(Workspace, ws.id)
    members = session.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == ws.id))
    return WorkspaceDetail(id=ws.id, name=ws.name, role=ws.role, members=members,
                           form_path=f"/webhooks/form/{workspace.form_key}" if ws.is_admin else None)


@router.get("/current/setup")
def setup(session: SessionDep, ws: WsDep) -> list[SetupStep]:
    """The first-time setup checklist, worked out from what the workspace already has."""
    def has(model, *where) -> bool:
        return session.scalar(select(func.count()).select_from(model).where(model.workspace_id == ws.id, *where)) > 0

    members = session.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == ws.id))
    return [
        SetupStep(id="profile", label="Describe your company", href="/profiles", admin_only=True,
                  help="One sentence is enough: GigScout fills in services, skills and what to avoid.",
                  done=has(AgencyProfileRecord)),
        SetupStep(id="sources", label="Choose where to look", href="/admin/sources", admin_only=True,
                  help="Add sites from the library for your kind of company, or switch built-in ones off.",
                  done=has(Connector) or has(SourceToggle)),
        SetupStep(id="run", label="Run the agents", href="/runs", admin_only=False,
                  help="Watch them search, judge and shortlist leads live (a few minutes).",
                  done=has(Run, Run.status == "succeeded")),
        SetupStep(id="digest", label="Get the best leads by email", href="/admin/workspace", admin_only=True,
                  help="A short daily email (or Slack post) with the new leads worth a call.",
                  done=has(DigestSettings, DigestSettings.enabled.is_(True))),
        SetupStep(id="team", label="Invite your team", href="/admin/users", admin_only=True,
                  help="Sales colleagues can work leads and start runs; admins manage settings.",
                  done=members > 1),
        SetupStep(id="outcome", label="Mark a lead won or lost", href="/leads", admin_only=False,
                  help="Outcomes teach GigScout what your company wins, and lift similar leads.",
                  done=has(LeadState, LeadState.status.in_(("won", "lost")))),
    ]


@router.patch("/current")
def rename(body: WorkspaceCreate, session: SessionDep, ws: AdminDep) -> WorkspaceDetail:
    workspace = session.get(Workspace, ws.id)
    audit(session, ws, "workspace.rename", str(ws.id), before=workspace.name, after=body.name.strip())
    workspace.name = body.name.strip()
    session.commit()
    return current(session, ws.__class__(ws.id, workspace.name, ws.role, ws.user, ws.index))


@router.post("/current/form-key")
def rotate_form_key(session: SessionDep, ws: AdminDep) -> WorkspaceDetail:
    """A new website form address; the old one stops working at once (use it if the address leaked)."""
    workspace = session.get(Workspace, ws.id)
    workspace.form_key = secrets.token_urlsafe(24)
    audit(session, ws, "workspace.form_key_rotated", str(ws.id))
    session.commit()
    return current(session, ws)
