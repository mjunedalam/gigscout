"""Connecting outside accounts by signing in (OAuth): Upwork."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse

from gigscout.upwork import UpworkError
from gigscout.web.deps import AdminDep, PlatformDep, SessionDep, audit
from gigscout.web.schemas import IntegrationStatusOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/upwork", tags=["integrations"])

SETUP_HELP = ("Upwork is not set up: add GIGSCOUT_UPWORK_CLIENT_ID and GIGSCOUT_UPWORK_CLIENT_SECRET (an approved "
              "Upwork API key) to apps/api/.env")
RETURN_TO = "/admin/sources"


@router.get("")
def upwork_status(platform: PlatformDep, _: AdminDep) -> IntegrationStatusOut:
    return IntegrationStatusOut(**platform.upwork.status())


@router.post("/connect")
def connect_upwork(platform: PlatformDep, admin: AdminDep) -> dict:
    """Where to send the admin to sign in to Upwork and allow GigScout to search jobs."""
    if not platform.upwork.configured:
        raise HTTPException(status.HTTP_409_CONFLICT, SETUP_HELP)
    return {"url": platform.upwork.start(admin.email)}


@router.get("/callback", include_in_schema=False)
def upwork_callback(
    platform: PlatformDep, session: SessionDep, state: str = "", code: str = "", error: str = "",
) -> RedirectResponse:
    """Upwork sends the browser back here. Our session cookie is SameSite=strict and does not come along on this
    cross-site redirect, so the one-time state (bound to the admin who started, valid ten minutes) authorises it."""
    if error or not code:
        return _back("error", "Upwork sign-in was cancelled")
    try:
        admin_email = platform.upwork.finish(code, state)
    except UpworkError as exc:
        return _back("error", str(exc))
    audit(session, admin_email, "upwork.connect")
    session.commit()
    platform.bus.publish("source.added", {"name": "Upwork", "by": admin_email})
    return _back("connected")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_upwork(platform: PlatformDep, session: SessionDep, admin: AdminDep) -> None:
    platform.upwork.disconnect()
    audit(session, admin, "upwork.disconnect")
    session.commit()


def _back(result: str, message: str = "") -> RedirectResponse:
    query = urlencode({"upwork": result, **({"message": message[:200]} if message else {})})
    return RedirectResponse(f"{RETURN_TO}?{query}", status_code=status.HTTP_303_SEE_OTHER)
