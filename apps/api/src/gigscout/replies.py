"""Client replies: what a reply means, and a draft answer for a person to approve.

The LLM reads replies when one is running; plain keyword rules cover offline use and LLM failures. Reply text comes
from outside, so it is treated as information about the client, never as instructions.
"""

import logging
import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from gigscout.models import AgencyProfile, Lead, OutreachText
from gigscout.outreach import BODY_MAX, OutreachDraft, one_line, single_address
from gigscout.store.knowledge import Evidence, format_evidence

log = logging.getLogger(__name__)

Intent = Literal["interested", "meeting", "question", "not_now", "not_interested", "out_of_office", "unsubscribe"]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]
NO_ANSWER = {"not_interested", "out_of_office", "unsubscribe"}  # nothing to write back
LEAD_STATUS = {"meeting": "proposal", "not_interested": "lost", "unsubscribe": "lost"}  # where the lead moves
REPLY_MAX = 20_000
QUOTE_START = re.compile(r"^(On .{5,200} wrote:|-{2,}\s*Original Message\s*-{2,}|From: .+|Sent from my .+)$",
                         re.IGNORECASE)

RULES: list[tuple[Intent, re.Pattern[str]]] = [
    ("unsubscribe", re.compile(r"\b(unsubscribe|remove me|stop (emailing|contacting)|do not contact)\b", re.I)),
    ("out_of_office", re.compile(r"\b(out of (the )?office|on (annual )?leave|auto(matic)?[- ]?reply|"
                                 r"away until|limited access to email)\b", re.I)),
    ("not_interested", re.compile(r"\b(not interested|no thanks|no, thank|we('ve| have) (already )?(hired|chosen|"
                                  r"found|gone with)|position (has been|is) filled|not a fit|pass on this)\b", re.I)),
    ("meeting", re.compile(r"\b(call|meeting|meet|zoom|teams|calendly|schedule|available (on|at)|"
                           r"what time|book a)\b", re.I)),
    ("not_now", re.compile(r"\b(not (right )?now|maybe later|next (month|quarter|year)|reach out (again )?(in|after)|"
                           r"circle back|on hold)\b", re.I)),
    ("question", re.compile(r"\?|\b(how much|what would|can you|could you|do you)\b", re.I)),
    ("interested", re.compile(r"\b(interested|sounds good|tell me more|send (me|over)|let'?s talk|keen)\b", re.I)),
]


MEETING = next(pattern for name, pattern in RULES if name == "meeting")


class ReplyRead(BaseModel):
    """What a client's reply means for the deal."""

    intent: Intent = Field(description="interested | meeting (wants a call) | question | not_now | not_interested | "
                                       "out_of_office (an auto-reply) | unsubscribe")
    summary: str = Field(description="One sentence: what the client said and wants, in plain words", max_length=300)


class ReplyReader(Protocol):
    def read_reply(self, profile: AgencyProfile, lead: Lead, original: str, reply: str) -> ReplyRead: ...

    def draft_answer(self, profile: AgencyProfile, lead: Lead, original: str, reply: str, intent: str,
                     evidence: str) -> OutreachText: ...


def strip_quoted(text: str) -> str:
    """Only what the client wrote: drop the quoted thread and signatures under it."""
    kept = []
    for line in text.replace("\r\n", "\n").splitlines():
        stripped = line.strip()
        if QUOTE_START.match(stripped):
            break
        if not stripped.startswith(">"):
            kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()[:REPLY_MAX]


def rule_read(reply: str) -> ReplyRead:
    text = strip_quoted(reply)
    intent: Intent = next((name for name, pattern in RULES if pattern.search(text)), "interested")
    first = one_line(text, 200)
    return ReplyRead(intent=intent, summary=first or "Empty reply")


def read_reply(profile: AgencyProfile, lead: Lead, original: str, reply: str, reader: object | None) -> tuple[
        ReplyRead, Literal["ai", "rules"]]:
    if reader is None or not hasattr(reader, "read_reply"):
        return rule_read(reply), "rules"
    try:
        read = reader.read_reply(profile, lead, original, strip_quoted(reply))
    except Exception:
        log.warning("Reading a reply with the LLM failed for %s; using rules", lead.id, exc_info=True)
        return rule_read(reply), "rules"
    if read.intent in ("interested", "question") and MEETING.search(strip_quoted(reply)):
        read = read.model_copy(update={"intent": "meeting"})  # asking for a call is the strongest signal
    return read, "ai"


def template_answer(profile: AgencyProfile, lead: Lead, intent: str, to: str | None, subject: str) -> OutreachDraft:
    client = lead.client
    greeting = f"Hi {client.name}," if client and client.name else "Hi,"
    middle = {
        "meeting": "Great, happy to talk. Here are a few times that work for us; tell me which suits you, or send "
                   "a time that is easier:\n\n- \n- \n- ",
        "question": "Thanks for the question. ",
        "not_now": "Understood, thanks for letting me know. I will check back in a few weeks; if anything changes "
                   "sooner, just reply here.",
    }.get(intent, f"Thanks for getting back to me about {one_line(lead.title, 120)}. The next step I would suggest "
                  "is a short call to go through scope and timing. When would suit you?")
    address = single_address(to)
    return OutreachDraft(channel="email" if address else "bid", to=address,
                         subject=one_line(f"Re: {subject.removeprefix('Re: ')}") if address else "",
                         body="\n\n".join([greeting, middle, f"Best,\n{profile.name}"])[:BODY_MAX])


def draft_answer(profile: AgencyProfile, lead: Lead, original: str, reply: str, intent: str, to: str | None,
                 subject: str, writer: object | None, evidence: tuple[Evidence, ...] = ()) -> OutreachDraft:
    draft = template_answer(profile, lead, intent, to, subject)
    if writer is None or not hasattr(writer, "draft_answer"):
        return draft
    try:
        text = writer.draft_answer(profile, lead, original, strip_quoted(reply), intent, format_evidence(evidence))
    except Exception:
        log.warning("Answer draft by the LLM failed for %s; using the template", lead.id, exc_info=True)
        return draft
    if not text.body.strip():
        return draft
    return OutreachDraft(channel=draft.channel, to=draft.to, subject=draft.subject,
                         body=text.body.strip()[:BODY_MAX], source="ai")
