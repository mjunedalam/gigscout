"""The first message to a lead: an email when we know who to write to, otherwise bid copy for the marketplace.

The LLM writes it when one is running; a plain template covers offline runs and LLM failures. People always see
and edit the draft before anything is sent.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Literal, Protocol

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field, field_validator

from gigscout.config import Settings
from gigscout.mail import deliver
from gigscout.models import AgencyProfile, Lead, OutreachText
from gigscout.store.knowledge import Claim, Evidence, KnowledgeBase, format_evidence

log = logging.getLogger(__name__)

Channel = Literal["email", "bid"]
SUBJECT_MAX = 200
BODY_MAX = 5000


class Drafter(Protocol):
    def draft_outreach(self, profile: AgencyProfile, lead: Lead, pitch: str, channel: str,
                       evidence: str = "") -> OutreachText: ...


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


def single_address(value: str | None) -> str | None:
    """Exactly one valid address, normalised; anything else (lists, display names, junk) is None."""
    if not value or any(c in value for c in ",;<>\r\n"):
        return None
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def one_line(text: str, limit: int = SUBJECT_MAX) -> str:
    return " ".join(text.split())[:limit]


def template_draft(profile: AgencyProfile, lead: Lead, pitch: str, evidence: Sequence[Evidence] = ()) -> OutreachDraft:
    client = lead.client
    email = single_address(client.email) if client else None  # lead data is untrusted: one recipient, or a bid
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
        f"Relevant to this: {one_line(evidence[0].title, 120)}." if evidence else "",
        "Would a short call this week be useful? I can walk you through how we would approach it.",
        f"Best,\n{profile.name}",
    ]
    return OutreachDraft(
        channel="email" if email else "bid", to=email, subject=f"Re: {title}" if email else "",
        body="\n\n".join(p for p in paragraphs if p),
    )


def follow_up_draft(profile: AgencyProfile, lead: Lead, to: str, subject: str, original: str) -> OutreachDraft:
    """A short nudge in the same thread, quoting the first message."""
    client = lead.client
    quoted = "\n".join(f"> {line}" for line in original.strip().splitlines())
    paragraphs = [
        f"Hi {client.name}," if client and client.name else "Hi,",
        f"Just following up on my note about {one_line(lead.title, 150)}. "
        "If the timing is not right, no problem: a one-line reply and I will not chase.",
        f"Best,\n{profile.name}",
        quoted,
    ]
    return OutreachDraft(channel="email", to=to, subject=one_line(f"Re: {subject.removeprefix('Re: ')}"),
                         body="\n\n".join(paragraphs)[:BODY_MAX])


def draft_outreach(profile: AgencyProfile, lead: Lead, pitch: str, drafter: Drafter | None,
                   evidence: Sequence[Evidence] = ()) -> OutreachDraft:
    draft = template_draft(profile, lead, pitch, evidence)
    if drafter is None:
        return draft
    try:
        text = drafter.draft_outreach(profile, lead, pitch, draft.channel, evidence=format_evidence(evidence))
    except Exception:
        log.warning("Outreach draft by the LLM failed for %s; using the template", lead.id, exc_info=True)
        return draft
    if not text.body.strip():
        return draft
    subject = one_line(text.subject) or draft.subject if draft.channel == "email" else ""
    return OutreachDraft(channel=draft.channel, to=draft.to, subject=subject, body=text.body.strip()[:BODY_MAX],
                         source="ai")


@dataclass(frozen=True)
class Grounded:
    """A draft, the company documents it drew on, and each of its claims checked against them."""

    draft: OutreachDraft
    evidence: list[dict] | None
    claims: list[dict] | None


def lead_query(lead: Lead) -> str:
    return " ".join([lead.title, ", ".join(lead.skills), lead.description[:600]])


def grounded_draft(profile: AgencyProfile, lead: Lead, pitch: str, drafter: Drafter | None,
                   knowledge: KnowledgeBase | None) -> Grounded:
    """Draft from the company's own documents when it has any, then check every claim the draft makes."""
    if knowledge is None or knowledge.count() == 0:
        return Grounded(draft_outreach(profile, lead, pitch, drafter), None, None)
    evidence = knowledge.search(lead_query(lead))
    draft = draft_outreach(profile, lead, pitch, drafter, evidence)
    return Grounded(draft, evidence_out(evidence), claims_out(knowledge.check_claims(draft.body, evidence)))


def recheck(body: str, knowledge: KnowledgeBase | None) -> list[dict] | None:
    """After a person edits a draft: check its claims again."""
    if knowledge is None or knowledge.count() == 0:
        return None
    return claims_out(knowledge.check_claims(body, ()))


def evidence_out(evidence: Sequence[Evidence]) -> list[dict]:
    return [{"doc_id": e.doc_id, "title": e.title, "kind": e.kind, "similarity": e.similarity,
             "excerpt": " ".join(e.text.split())[:280]} for e in evidence]


def claims_out(claims: Sequence[Claim]) -> list[dict]:
    return [{"sentence": c.sentence, "supported": c.supported, "source": c.source, "similarity": c.similarity}
            for c in claims]


def send_email(settings: Settings, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["To"] = to
    message.set_content(body)
    deliver(settings, message)
