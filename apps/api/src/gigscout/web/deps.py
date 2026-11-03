"""Request-scoped dependencies: the platform, a DB session, the signed-in user, and audit logging."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from gigscout.platform.container import Platform
from gigscout.platform.security import hash_token
from gigscout.platform.tables import AuditLog, AuthToken, User

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


def require_admin(user: UserDep) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


AdminDep = Annotated[User, Depends(require_admin)]


def audit(session: Session, actor: User | str, action: str, target: str = "", **detail) -> None:
    """Record who changed what. The caller commits, so the audit row lands with the change it describes."""
    name = actor if isinstance(actor, str) else actor.email
    session.add(AuditLog(actor=name, action=action, target=target, detail=detail))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
