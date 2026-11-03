"""Admin console: users, system health, sources, configuration and the audit log."""

import platform as pyplatform
import time
from collections import Counter

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import SecretStr
from sqlalchemy import func, select

from gigscout.inbound import google_ads
from gigscout.platform.security import WeakPasswordError, hash_password
from gigscout.platform.tables import AuditLog, AuthToken, Run, User
from gigscout.web.deps import AdminDep, PlatformDep, SessionDep, audit
from gigscout.web.schemas import AuditOut, SourceHealth, SourceTestResult, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])

RECENT_RUNS_FOR_HEALTH = 20
SOURCE_TEST_QUERY = "web app"
SOURCE_TEST_LIMIT = 5


# --- users ------------------------------------------------------------------------------------------------------
@router.get("/users")
def list_users(session: SessionDep, _: AdminDep) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in session.scalars(select(User).order_by(User.id))]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, session: SessionDep, admin: AdminDep) -> UserOut:
    email = body.email.lower()
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(email=email, name=body.name, role=body.role, password_hash=_hash(body.password))
    session.add(user)
    session.flush()
    audit(session, admin, "user.create", email, role=body.role)
    session.commit()
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, session: SessionDep, admin: AdminDep) -> UserOut:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    demoting = (body.role == "member" or body.is_active is False) and user.role == "admin"
    if demoting and _active_admins(session) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Keep at least one active admin")
    if user.id == admin.id and body.is_active is False:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot deactivate yourself")
    changes = body.model_dump(exclude_none=True, exclude={"password"})
    for field, value in changes.items():
        setattr(user, field, value)
    if body.password:
        user.password_hash = _hash(body.password)
        changes["password"] = "reset"
    if body.password or body.is_active is False:
        session.query(AuthToken).filter(AuthToken.user_id == user.id).delete()  # sign them out everywhere
    audit(session, admin, "user.update", user.email, **changes)
    session.commit()
    return UserOut.model_validate(user)


# --- system -----------------------------------------------------------------------------------------------------
@router.get("/system")
def system(platform: PlatformDep, session: SessionDep, _: AdminDep) -> dict:
    settings = platform.settings
    deps = platform.service.deps
    return {
        "version": "0.2.0",
        "python": pyplatform.python_version(),
        "uptime_seconds": round(time.time() - platform.started_at),
        "llm": {
            "provider": settings.llm_provider, "model": settings.llm_model,
            "available": deps.chat_model is not None, "reachable_now": _ollama_up(settings),
        },
        "embedding_model": settings.embedding_model,
        "vector_store": {"leads": deps.index.count(), "path": str(settings.chroma_path)},
        "database": {"url": _redact_url(settings.resolved_database_url),
                     "users": session.scalar(select(func.count()).select_from(User)),
                     "runs": session.scalar(select(func.count()).select_from(Run))},
        "scheduler": {"running": platform.schedules.running, "jobs": platform.schedules.job_count,
                      "timezone": settings.timezone},
        "inbound": {"google_ads_webhook": platform.service.inbound_enabled},
        "live_clients": platform.bus.subscriber_count,
        "mlflow": {"enabled": settings.mlflow_enabled, "tracking_uri": _redact_url(settings.mlflow_tracking_uri)},
    }


@router.get("/settings")
def effective_settings(platform: PlatformDep, _: AdminDep) -> dict:
    """Read-only view of the running configuration. Secrets are masked; change values in .env and restart."""
    values = platform.settings.model_dump(mode="python")
    return {key: ("••••••" if isinstance(value, SecretStr) else _redact_urls(_jsonable(value)))
            for key, value in values.items()}


# --- sources ----------------------------------------------------------------------------------------------------
@router.get("/sources")
def source_health(platform: PlatformDep, session: SessionDep, _: AdminDep) -> list[SourceHealth]:
    runs = list(session.scalars(select(Run).order_by(Run.created_at.desc()).limit(RECENT_RUNS_FOR_HEALTH)))
    failures: Counter[str] = Counter()
    last_error: dict[str, str] = {}
    for run in runs:
        for error in run.errors:
            name = error.split(":", 1)[0]
            failures[name] += 1
            last_error.setdefault(name, error)
    pulled = [
        SourceHealth(name=n, channel="pull", enabled=True, recent_failures=failures[n], last_error=last_error.get(n))
        for n in platform.service.deps.sources
    ]
    pushed = SourceHealth(name=google_ads.SOURCE_NAME, channel="push", enabled=platform.service.inbound_enabled,
                          recent_failures=0)
    return [*pulled, pushed]


@router.post("/sources/{name}/test")
def test_source(name: str, platform: PlatformDep, session: SessionDep, admin: AdminDep) -> SourceTestResult:
    source = platform.service.deps.sources.get(name)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown pull source")
    started = time.perf_counter()
    try:
        leads = source.fetch([SOURCE_TEST_QUERY], SOURCE_TEST_LIMIT)
        result = SourceTestResult(name=name, ok=True, count=len(leads), latency_ms=_ms(started),
                                  sample=[lead.title for lead in leads[:3]])
    except Exception as exc:
        result = SourceTestResult(name=name, ok=False, latency_ms=_ms(started), error=f"{type(exc).__name__}: {exc}")
    audit(session, admin, "source.test", name, ok=result.ok)
    session.commit()
    return result


# --- audit ------------------------------------------------------------------------------------------------------
@router.get("/audit")
def audit_log(session: SessionDep, _: AdminDep, limit: int = Query(default=100, ge=1, le=1000)) -> list[AuditOut]:
    rows = session.scalars(select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(limit))
    return [AuditOut.model_validate(r) for r in rows]


def _hash(password: str) -> str:
    try:
        return hash_password(password)
    except WeakPasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _active_admins(session) -> int:
    return session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active))


def _ollama_up(settings) -> bool:
    if settings.llm_provider == "none":
        return False
    try:
        return httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=1.5).is_success
    except httpx.HTTPError:
        return False


def _redact_url(url: str) -> str:
    """Hide credentials in URLs like postgresql://user:pass@host/db."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    return f"{scheme}://••••@{rest.split('@', 1)[1]}"


def _redact_urls(value):
    """Masks credentials in any URL-shaped setting (database, MLflow, Ollama, feeds), not just known fields."""
    if isinstance(value, str):
        return _redact_url(value)
    if isinstance(value, list):
        return [_redact_urls(v) for v in value]
    return value


def _jsonable(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
