"""Google Ads lead form assets → inbound leads.

The agency runs Google Ads with a lead form; Google POSTs every submission to our webhook
(`POST /webhooks/google-ads`). The payload carries a shared `google_key` that we verify, then the
submission becomes an `inbound` Lead in the same memory as marketplace leads, so it is ranked alongside them.
"""

import re
import secrets
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from gigscout.models import Budget, Client, Lead

SOURCE_NAME = "google_ads"
MAX_ANSWER_CHARS = 2000
_AMOUNT = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Standard lead form column ids → Client fields
_NAME_COLUMNS = ("FULL_NAME", "FIRST_NAME", "LAST_NAME")
_CLIENT_COLUMNS = {"EMAIL": "email", "PHONE_NUMBER": "phone", "COMPANY_NAME": "name", "COUNTRY": "country"}


class LeadFormColumn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    column_id: str | None = Field(default=None, max_length=200)
    column_name: str | None = Field(default=None, max_length=500)
    string_value: str = Field(default="", max_length=MAX_ANSWER_CHARS)


class GoogleAdsLeadForm(BaseModel):
    """The webhook body Google sends for one lead form submission."""

    model_config = ConfigDict(extra="ignore")

    lead_id: str = Field(min_length=1, max_length=200)
    google_key: str = Field(max_length=500)
    user_column_data: list[LeadFormColumn] = Field(default_factory=list, max_length=100)
    campaign_id: int | str | None = None
    form_id: int | str | None = None
    is_test: bool = False


def key_matches(form: GoogleAdsLeadForm, expected: str) -> bool:
    return secrets.compare_digest(form.google_key.encode(), expected.encode())


def to_lead(form: GoogleAdsLeadForm, received_at: datetime | None = None) -> Lead:
    answers = {c.column_id or c.column_name or "": c.string_value.strip() for c in form.user_column_data}
    name = " ".join(answers[c] for c in _NAME_COLUMNS if answers.get(c)) or None
    client = Client(**{field: answers[col] for col, field in _CLIENT_COLUMNS.items() if answers.get(col)})
    who = client.name or name or "a prospect"
    return Lead(
        id=f"{SOURCE_NAME}:{form.lead_id}",
        source=SOURCE_NAME,
        title=f"Inbound enquiry from {who}",
        description=_describe(form, name),
        url=f"https://ads.google.com/aw/campaigns?campaignId={form.campaign_id}" if form.campaign_id else "",
        kind="inbound",
        budget=_budget(form),
        posted_at=received_at or datetime.now(UTC),
        client=client if client != Client() else None,
    )


def _describe(form: GoogleAdsLeadForm, contact_name: str | None) -> str:
    lines = [f"Contact: {contact_name}"] if contact_name else []
    standard = {*_NAME_COLUMNS, *_CLIENT_COLUMNS}
    for c in form.user_column_data:
        if c.column_id not in standard and c.string_value.strip():
            lines.append(f"{c.column_name or c.column_id}: {c.string_value.strip()}")
    return "\n".join(lines) or "Lead form submitted without answers."


def _budget(form: GoogleAdsLeadForm) -> Budget | None:
    """Pick up a custom 'budget' question if the form has one (e.g. "$5,000 - $10,000")."""
    for c in form.user_column_data:
        label = f"{c.column_id or ''} {c.column_name or ''}".lower()
        if "budget" in label:
            amounts = [float(a.replace(",", "")) for a in _AMOUNT.findall(c.string_value)]
            if amounts:
                return Budget(minimum=min(amounts), maximum=max(amounts), currency="USD", kind="fixed")
    return None
