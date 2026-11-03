"""Webhooks for inbound enquiries: the company's own website form, Typeform, and Meta lead ads.

Unauthenticated by design (the senders cannot log in); each is authenticated its own way: a secret key in the form
URL, Typeform's and Meta's HMAC signatures over the raw body, and Meta's verify token for the subscription check.
"""

import hashlib
import hmac
import json
import logging
import re
import threading
import time
from collections import defaultdict, deque

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import SecretStr

from gigscout.inbound import forms
from gigscout.web.deps import PlatformDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["public"])

MAX_BODY_BYTES = 64_000
FORM_LIMIT_PER_HOUR = 10  # per sender address: a contact form, not a bulk API
GRAPH_LEAD_URL = "https://graph.facebook.com/v21.0/{lead_id}"
_LEADGEN_ID = re.compile(r"^\d{5,30}$")
THANKS_PAGE = (
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    "<title>Thank you</title>"
    '<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem">'
    "<h1>Thank you</h1><p>We received your message and will get back to you shortly.</p></body>"
)


class _SenderLimit:
    def __init__(self, per_hour: int) -> None:
        self._per_hour = per_hour
        self._seen: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, sender: str) -> bool:
        now = time.monotonic()
        with self._lock:
            calls = self._seen[sender]
            while calls and now - calls[0] > 3600:
                calls.popleft()
            if len(calls) >= self._per_hour:
                return False
            calls.append(now)
            return True


_form_limit = _SenderLimit(FORM_LIMIT_PER_HOUR)


@router.post("/form/{key}", response_model=None)
async def website_form(key: str, request: Request, platform: PlatformDep) -> HTMLResponse | dict:
    """Point your contact form here (method POST): a plain HTML form gets a thank-you page, fetch() gets JSON."""
    expected = platform.settings.website_form_key
    if expected is None or not _same(key, expected):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    body = await _body(request)
    is_html_form = request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data"))
    sender = request.client.host if request.client else "unknown"
    if not _form_limit.allow(sender):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many submissions; please try again later")
    raw = dict(await request.form()) if is_html_form else _json(body)
    fields = forms.clean({k: v for k, v in raw.items() if isinstance(v, str | int | float | list)})
    result = "stored"
    if forms.is_spam(fields):
        log.info("Dropped a website form submission that filled the honeypot")  # answer as if stored
    elif not fields:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The form was empty")
    else:
        native_id = hashlib.sha256(repr(sorted(fields.items())).encode()).hexdigest()[:24]  # a double submit is one
        result = _ingest(platform, forms.to_lead("website_form", native_id, fields, "Website"))
    return HTMLResponse(THANKS_PAGE) if is_html_form else {"status": result}


@router.post("/typeform")
async def typeform(request: Request, platform: PlatformDep) -> dict:
    secret = platform.settings.typeform_webhook_secret
    if secret is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Typeform webhook is not enabled")
    body = await _body(request)
    if not forms.signature_matches(body, secret.get_secret_value(), request.headers.get("typeform-signature"),
                                   prefix="sha256=", b64=True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    token, fields = forms.typeform_fields(_json(body))
    if not token:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Not a form response")
    return {"status": _ingest(platform, forms.to_lead("typeform", token, fields, "Typeform"))}


@router.get("/meta", response_class=PlainTextResponse)
def meta_verify(
    platform: PlatformDep, mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge", max_length=200),
) -> str:
    """Meta checks the subscription once by echoing a challenge when the verify token matches."""
    expected = platform.settings.meta_verify_token
    if expected is None or mode != "subscribe" or not _same(token, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")
    return challenge


@router.post("/meta")
async def meta_leadgen(request: Request, platform: PlatformDep) -> dict:
    s = platform.settings
    if not (s.meta_app_secret and s.meta_verify_token and s.meta_page_access_token):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meta lead ads webhook is not enabled")
    body = await _body(request)
    if not forms.signature_matches(body, s.meta_app_secret.get_secret_value(),
                                   request.headers.get("x-hub-signature-256"), prefix="sha256=", b64=False):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    results = []
    for entry in _json(body).get("entry") or []:
        for change in entry.get("changes") or []:
            lead_id = str((change.get("value") or {}).get("leadgen_id") or "")
            if change.get("field") == "leadgen" and _LEADGEN_ID.match(lead_id):
                results.append(_meta_lead(platform, lead_id, s.meta_page_access_token))
    return {"status": "stored" if "stored" in results else "duplicate" if results else "ignored"}


def _meta_lead(platform, lead_id: str, token: SecretStr) -> str:
    """The webhook carries only an id: the answers come from the Graph API with the page token."""
    try:
        response = httpx.get(GRAPH_LEAD_URL.format(lead_id=lead_id), params={"fields": "field_data,created_time"},
                             headers={"Authorization": f"Bearer {token.get_secret_value()}"}, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Could not read Meta lead %s (%s)", lead_id, type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not read the lead from Meta") from None
    fields = forms.meta_fields(response.json())
    return _ingest(platform, forms.to_lead("meta_lead_ads", lead_id, fields, "Meta lead ad"))


def _ingest(platform, lead) -> str:
    stored = platform.service.ingest_inbound(lead)
    if stored:
        platform.bus.publish("lead.inbound", {"id": lead.id, "title": lead.title})
    return "stored" if stored else "duplicate"


async def _body(request: Request) -> bytes:
    if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Too large")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Too large")
    return body


def _json(body: bytes) -> dict:
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected JSON") from None
    if not isinstance(data, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected a JSON object")
    return data


def _same(given: str, expected: SecretStr) -> bool:
    return hmac.compare_digest(given.encode(), expected.get_secret_value().encode())
