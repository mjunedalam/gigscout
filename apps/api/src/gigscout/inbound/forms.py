"""Inbound enquiries from forms: the company's own website, Typeform, and Meta (Facebook/Instagram) lead ads.

Every channel ends in the same builder: submitted fields -> an `inbound` Lead. Common field names (name, email,
company, phone, country, budget, message) fill the client and budget; everything else goes into the description.
"""

import base64
import hashlib
import hmac
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from gigscout.models import Budget, Client, Lead

MAX_FIELDS = 40
MAX_VALUE_CHARS = 2000
_AMOUNT = re.compile(r"\d[\d,]*(?:\.\d+)?")

_NAME = ("name", "full_name", "fullname", "your_name", "contact_name")
_FIRST, _LAST = ("first_name", "firstname"), ("last_name", "lastname", "surname")
_CLIENT = {
    "email": ("email", "email_address", "work_email", "your_email"),
    "phone": ("phone", "phone_number", "telephone", "mobile"),
    "name": ("company", "company_name", "organisation", "organization", "business"),
    "country": ("country", "location"),
}
_BUDGET = ("budget", "project_budget", "estimated_budget")
_MESSAGE = ("message", "details", "project", "description", "how_can_we_help", "enquiry", "inquiry", "comments")
HONEYPOT = ("website_url", "_gotcha")  # hidden fields people never fill; bots do


def normalise(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def clean(fields: Mapping[str, object]) -> dict[str, str]:
    """Plain string answers, keys normalised, sizes capped (submissions are untrusted)."""
    out: dict[str, str] = {}
    for key, value in list(fields.items())[:MAX_FIELDS]:
        if isinstance(value, list | tuple):
            value = ", ".join(str(v) for v in value)
        text = str(value or "").strip()[:MAX_VALUE_CHARS]
        if text and normalise(str(key)):
            out[normalise(str(key))[:80]] = text
    return out


def is_spam(fields: Mapping[str, str]) -> bool:
    return any(fields.get(h) for h in HONEYPOT)


def to_lead(source: str, native_id: str, fields: Mapping[str, str], label: str, url: str = "",
            received_at: datetime | None = None) -> Lead:
    used: set[str] = set()

    def pick(keys: tuple[str, ...]) -> str | None:
        for key in keys:
            if fields.get(key):
                used.add(key)
                return fields[key]
        return None

    contact = pick(_NAME) or " ".join(filter(None, (pick(_FIRST), pick(_LAST)))) or None
    client = Client(**{f: v for f, keys in _CLIENT.items() if (v := pick(keys))})
    budget_text, message = pick(_BUDGET), pick(_MESSAGE)
    who = client.name or contact or "a prospect"
    lines = [f"Contact: {contact}"] if contact else []
    if message:
        lines.append(message)
    lines += [f"{key.replace('_', ' ').capitalize()}: {value}" for key, value in fields.items()
              if key not in used and key not in HONEYPOT]
    if budget_text:
        lines.append(f"Budget: {budget_text}")
    return Lead(
        id=f"{source}:{native_id}", source=source, kind="inbound", url=url,
        title=f"{label} enquiry from {who}", description="\n".join(lines) or "Form submitted without answers.",
        budget=_budget(budget_text), posted_at=received_at or datetime.now(UTC),
        client=client if client != Client() else None,
    )


def _budget(text: str | None) -> Budget | None:
    amounts = [float(a.replace(",", "")) for a in _AMOUNT.findall(text or "")]
    if not amounts:
        return None
    return Budget(minimum=min(amounts), maximum=max(amounts), currency="USD" if "$" in text else None, kind="fixed")


def signature_matches(body: bytes, secret: str, header: str | None, *, prefix: str, b64: bool) -> bool:
    """HMAC-SHA256 webhook signatures: Typeform sends base64 ('sha256=...'), Meta sends hex ('sha256=...')."""
    if not header or not header.startswith(prefix):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode() if b64 else digest.hex()
    return hmac.compare_digest(header[len(prefix):].encode(), expected.encode())


def typeform_fields(payload: dict) -> tuple[str, dict[str, str]]:
    """(response token, field title -> answer) from a Typeform form_response webhook."""
    response = payload.get("form_response") or {}
    titles = {f.get("id"): f.get("title") or f.get("ref") or "" for f in (response.get("definition") or {}).get(
        "fields") or []}
    answers: dict[str, object] = {}
    for answer in response.get("answers") or []:
        field = answer.get("field") or {}
        kind = answer.get("type")
        value = answer.get(kind)
        if kind == "choice":
            value = (value or {}).get("label")
        elif kind == "choices":
            value = (value or {}).get("labels")
        title = titles.get(field.get("id")) or field.get("ref") or field.get("id") or kind
        answers[_typeform_key(kind, title)] = value
    return str(response.get("token") or ""), clean(answers)


def _typeform_key(kind: str | None, title: str) -> str:
    """Typed answers name themselves (an 'email' answer is the email, whatever the question said)."""
    return {"email": "email", "phone_number": "phone"}.get(kind or "", title)


def meta_fields(lead: dict) -> dict[str, str]:
    """field_data from the Graph API ({name, values}) -> answers."""
    return clean({item.get("name", ""): item.get("values") or [] for item in lead.get("field_data") or []})
