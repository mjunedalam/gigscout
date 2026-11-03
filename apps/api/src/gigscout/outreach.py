"""The first message to a lead: an email when we know who to write to, otherwise bid copy for the marketplace.

The LLM writes it when one is running; a plain template covers offline runs and LLM failures. People always see
and edit the draft before anything is sent.
"""

import logging
from email.message import EmailMessage
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from gigscout.config import Settings
from gigscout.mail import deliver
from gigscout.models import AgencyProfile, Lead, OutreachText

log = logging.getLogger(__name__)

Channel = Literal["email", "bid"]
SUBJECT_MAX = 200
BODY_MAX = 5000


class Drafter(Protocol):
    def draft_outreach(self, profile: AgencyProfile, lead: Lead, pitch: str, channel: str) -> OutreachText: ...


class OutreachDraft(BaseModel):
    channel: Channel
    to: str | None = None
    subject: str = Field(default="", max_length=SUBJECT_MAX)
    body: str = Field(max_length=BODY_MAX)
    source: Literal["ai", "template"] = "template"

    @field_validator("to", "subject")
    @classmethod
    def _single_line(cls, value: str | None) -> str | None:
        if value and ("\r" in value or "\n" in value):
            raise ValueError("must be a single line")  # an email header: newlines would inject more headers
        return value


def one_line(text: str, limit: int = SUBJECT_MAX) -> str:
    return " ".join(text.split())[:limit]


def template_draft(profile: AgencyProfile, lead: Lead, pitch: str) -> OutreachDraft:
    client = lead.client
    email = client.email if client and client.email else None
    title = one_line(lead.title, 150)
    opening = {
        "inbound": f"Thanks for getting in touch about {title}.",
        "hiring": f"I saw you're hiring for {title}. Rather than a new hire, "
                  f"{profile.name} could take this on for you.",
        "contract": f"I saw you're looking for outside help with {title}.",
    }.get(lead.kind, f"I read your post: {title}.")
    about = f"{profile.name} is a {profile.company_type.lower()}"
    if profile.services:
        about += f" offering {', '.join(profile.services[:3])}"
    paragraphs = [
        f"Hi {client.name}," if client and client.name else "Hi,",
        opening,
        pitch.strip(),
        about + ".",
        "Would a short call this week be useful? I can walk you through how we would approach it.",
        f"Best,\n{profile.name}",
    ]
    return OutreachDraft(
        channel="email" if email else "bid", to=email, subject=f"Re: {title}" if email else "",
        body="\n\n".join(p for p in paragraphs if p),
    )


def draft_outreach(profile: AgencyProfile, lead: Lead, pitch: str, drafter: Drafter | None) -> OutreachDraft:
    draft = template_draft(profile, lead, pitch)
    if drafter is None:
        return draft
    try:
        text = drafter.draft_outreach(profile, lead, pitch, draft.channel)
    except Exception:
        log.warning("Outreach draft by the LLM failed for %s; using the template", lead.id, exc_info=True)
        return draft
    if not text.body.strip():
        return draft
    subject = one_line(text.subject) or draft.subject if draft.channel == "email" else ""
    return OutreachDraft(channel=draft.channel, to=draft.to, subject=subject, body=text.body.strip()[:BODY_MAX],
                         source="ai")


def send_email(settings: Settings, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["To"] = to
    message.set_content(body)
    deliver(settings, message)
