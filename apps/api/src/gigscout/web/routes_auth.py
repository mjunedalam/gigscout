"""Sign in / out. Sessions are opaque tokens in an HttpOnly, SameSite=Strict cookie (or a Bearer header)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select

from gigscout.platform.security import DUMMY_PASSWORD_HASH, hash_token, new_token, verify_password
from gigscout.platform.tables import AuthToken, User, utcnow
from gigscout.web.deps import SESSION_COOKIE, PlatformDep, SessionDep, UserDep, audit, bearer_or_cookie
from gigscout.web.schemas import LoginRequest, MeOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, platform: PlatformDep, session: SessionDep) -> dict:
    email = body.email.lower()
    key = f"{email}|{request.client.host if request.client else '-'}"
    if not (platform.login_limiter.try_attempt(key) and platform.account_limiter.try_attempt(email)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in a few minutes.")
    user = session.scalar(select(User).where(User.email == email))
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if user is None or not user.is_active or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    platform.login_limiter.reset(key)
    platform.account_limiter.reset(email)

    token = new_token()
    ttl = timedelta(hours=platform.settings.session_ttl_hours)
    session.execute(delete(AuthToken).where(AuthToken.expires_at <= datetime.now(UTC)))
    session.add(AuthToken(token_hash=hash_token(token), user_id=user.id, expires_at=datetime.now(UTC) + ttl))
    user.last_login_at = utcnow()
    audit(session, user, "auth.login")
    session.commit()

    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(ttl.total_seconds()), httponly=True, samesite="strict",
        secure=platform.settings.cookie_secure, path="/",
    )
    return {"user": _me(session, user).model_dump(mode="json")}  # token only in the HttpOnly cookie


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: SessionDep) -> None:
    token = bearer_or_cookie(request)
    if token:
        session.execute(delete(AuthToken).where(AuthToken.token_hash == hash_token(token)))
        session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: UserDep, session: SessionDep) -> MeOut:
    return _me(session, user)


def _me(session, user: User) -> MeOut:
    from gigscout.web.routes_workspaces import workspaces_of

    return MeOut(**UserOut.model_validate(user).model_dump(), workspaces=workspaces_of(session, user))
