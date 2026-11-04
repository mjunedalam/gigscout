"""Request-scoped dependencies: the platform, a DB session, the signed-in user, their workspace, and audit logging.

The browser says which workspace it is working in with the X-Workspace header (or ?workspace= where a header cannot
be set, e.g. EventSource). Without one, the user's first workspace is used. Platform admins may open any workspace.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gigscout.platform.container import Platform
from gigscout.platform.security import hash_token
from gigscout.platform.tables import AuditLog, AuthToken, Membership, User, Workspace
from gigscout.store.vector_store import LeadIndex

SESSION_COOKIE = "gigscout_session"


def get_platform(request: Request) -> Platform:
    return request.app.state.platform


PlatformDep = Annotated[Platform, Depends(get_platform)]


def get_session(platform: PlatformDep) -> Iterator[Session]:
    with platform.sessions() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def bearer_or_cookie(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request, session: SessionDep) -> User:
    token = bearer_or_cookie(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    record = session.get(AuthToken, hash_token(token))
    if record is None or _aware(record.expires_at) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    return user


UserDep = Annotated[User, Depends(current_user)]


@dataclass(frozen=True)
class Ws:
    """The workspace a request works in, who is asking, and their role there."""

    id: int
    name: str
    role: str  # owner | admin | member ("owner" for platform admins visiting)
    user: User
    index: LeadIndex

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")

    @property
    def email(self) -> str:
        return self.user.email


def current_workspace(request: Request, user: UserDep, session: SessionDep, platform: PlatformDep) -> Ws:
    wanted = request.headers.get("x-workspace") or request.query_params.get("workspace")
    memberships = {m.workspace_id: m.role for m in session.scalars(
        select(Membership).where(Membership.user_id == user.id))}
    if wanted:
        try:
            workspace_id = int(wanted)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad workspace id") from None
    elif memberships:
        workspace_id = min(memberships)
    elif user.role == "admin":
        workspace_id = session.scalar(select(Workspace.id).order_by(Workspace.id).limit(1)) or 0
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of any workspace")
    role = memberships.get(workspace_id) or ("owner" if user.role == "admin" else None)
    workspace = session.get(Workspace, workspace_id) if role else None
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")  # same answer whether it exists or not
    return Ws(workspace.id, workspace.name, role, user, platform.index_for(workspace.id))


WsDep = Annotated[Ws, Depends(current_workspace)]


def require_admin(ws: WsDep) -> Ws:
    """An owner or admin of the current workspace (platform admins count as owners everywhere)."""
    if not ws.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return ws


AdminDep = Annotated[Ws, Depends(require_admin)]


def require_platform_admin(user: UserDep) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admins only")
    return user


PlatformAdminDep = Annotated[User, Depends(require_platform_admin)]


def audit(session: Session, actor: "Ws | User | str", action: str, target: str = "", *,
          workspace_id: int | None = None, **detail) -> None:
    """Record who changed what, in the actor's workspace when there is one. The caller commits, so the audit row
    lands with the change it describes."""
    name = actor if isinstance(actor, str) else actor.email
    workspace_id = actor.id if isinstance(actor, Ws) else workspace_id
    session.add(AuditLog(actor=name, action=action, target=target, detail=detail, workspace_id=workspace_id))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
