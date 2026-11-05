"""The reply copilot: client replies come in (from the mailbox, or pasted by hand), the agents read what each one
means, move the lead along the pipeline, and draft an answer that waits for a person's approval like any pitch."""

import email
import email.policy
import imaplib
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from email.message import EmailMessage
from email.utils import parseaddr

from sqlalchemy import func, or_, select

from gigscout import replies as reply_lib
from gigscout.config import Settings
from gigscout.mail import SHARED_MAIL_DOMAINS
from gigscout.outreach import Drafter, claims_out, evidence_out, lead_query, single_address
from gigscout.platform import pipeline
from gigscout.platform.db import SessionFactory
from gigscout.platform.events import EventBus
from gigscout.platform.pitches import _profile_for
from gigscout.platform.scheduler import ScheduleManager
from gigscout.platform.tables import AGENT_AUTHOR, AuditLog, LeadState, Outreach, Reply, utcnow
from gigscout.store.vector_store import LeadIndex

log = logging.getLogger(__name__)

JOB_ID = "replies"
LOOKBACK_DAYS = 45  # only mail this recent can answer something we sent
MAX_PER_POLL = 200
IMAP_TIMEOUT = 30


@dataclass(frozen=True)
class Incoming:
    from_address: str | None
    subject: str
    body: str
    message_id: str | None
    in_reply_to: tuple[str, ...]  # In-Reply-To and References ids
    authenticated: bool = False  # our mail server saw DKIM or DMARC pass for the From domain


def same_party(incoming: Incoming, recipient: str | None) -> bool:
    """A reply moves the lead only if its sender is confirmed AND is the person (or company) we wrote to."""
    sender, wrote_to = single_address(incoming.from_address), single_address(recipient)
    if not incoming.authenticated or not sender or not wrote_to:
        return False
    if sender.lower() == wrote_to.lower():
        return True
    domain = sender.rsplit("@", 1)[1].lower()  # a colleague at the same company, but never on a shared provider
    return domain == wrote_to.rsplit("@", 1)[1].lower() and domain not in SHARED_MAIL_DOMAINS


def imap_ready(settings: Settings) -> bool:
    return bool(settings.imap_host and settings.imap_user and settings.imap_password)


class ReplyDesk:
    def __init__(self, sessions: SessionFactory, bus: EventBus, schedules: ScheduleManager, settings: Settings,
                 index_for: Callable[[int], LeadIndex], reader: Callable[[], Drafter | None]) -> None:
        self._sessions = sessions
        self._bus = bus
        self._schedules = schedules
        self._settings = settings
        self._index_for = index_for
        self._reader = reader  # the LLM when one is running; keyword rules otherwise
        self._polling = threading.Lock()

    def start(self) -> None:
        if imap_ready(self._settings):
            self._schedules.set_interval(JOB_ID, self._settings.imap_poll_minutes * 60, self.poll)

    def receive(self, workspace_id: int, outreach_id: int, body: str, from_address: str | None = None,
                subject: str = "", message_id: str | None = None, source: str = "email",
                actor: str = AGENT_AUTHOR, verified: bool = True) -> Reply | None:
        """Take in one reply to one of our messages. Returns None if this exact email was already taken in.

        An unverified reply (its sender could be forged) is recorded and answered as a draft, but moves nothing:
        a person decides what it means for the lead."""
        with self._sessions() as session:
            original = session.get(Outreach, outreach_id)
            if original is None or original.workspace_id != workspace_id:
                raise LookupError("Message not found")
            if message_id and session.scalar(select(Reply.id).where(
                    Reply.workspace_id == workspace_id, Reply.message_id == message_id)):
                return None
            lead = self._index_for(workspace_id).get(original.lead_id)
            profile = _profile_for(session, workspace_id, original.run_id)
            if lead is None or profile is None:
                raise LookupError("The lead or company profile behind this message is gone")
            reader = self._reader()
            read, read_by = reply_lib.read_reply(profile, lead, original.body, body, reader)
            reply = Reply(workspace_id=workspace_id, outreach_id=original.id, lead_id=original.lead_id,
                          from_address=single_address(from_address), subject=subject[:300],
                          body=reply_lib.strip_quoted(body) or body[:reply_lib.REPLY_MAX], message_id=message_id,
                          source=source, intent=read.intent, summary=read.summary, read_by=read_by,
                          verified=verified)
            session.add(reply)
            if verified:
                if original.status in ("sent", "no_reply"):
                    original.status = "replied"
                if read.intent != "out_of_office":
                    pipeline.mark(session, workspace_id, original.lead_id, "replied", actor)
                self._move_lead(session, workspace_id, original.lead_id, read.intent, actor)
            session.flush()
            if read.intent not in reply_lib.NO_ANSWER:
                reply.answer_id = self._draft_answer(session, workspace_id, original, reply, profile, lead, reader)
            session.add(AuditLog(actor=actor, action="reply.received", target=original.lead_id,
                                 workspace_id=workspace_id,
                                 detail={"intent": read.intent, "source": source, "outreach_id": original.id,
                                         "verified": verified}))
            session.commit()
            title = lead.title
        self._bus.publish("reply.received", {"id": reply.id, "lead_id": reply.lead_id, "title": title,
                                             "intent": reply.intent, "summary": reply.summary}, workspace_id)
        return reply

    def poll(self) -> int:
        """Read new mail and take in every reply to something we sent. Returns how many were new."""
        if not imap_ready(self._settings) or not self._polling.acquire(blocking=False):
            return 0
        try:
            messages = fetch_recent(self._settings)
        except (imaplib.IMAP4.error, OSError):
            log.warning("Reading the reply mailbox failed", exc_info=True)
            return 0
        finally:
            self._polling.release()
        taken = 0
        for incoming in messages:
            match = self.match(incoming)
            if match is None:
                continue
            try:
                taken += self.receive(match.workspace_id, match.id, incoming.body, incoming.from_address,
                                      incoming.subject, incoming.message_id,
                                      verified=same_party(incoming, match.to_address)) is not None
            except LookupError:
                continue
            except Exception:
                log.warning("Taking in a reply failed", exc_info=True)
        return taken

    def match(self, incoming: Incoming) -> Outreach | None:
        """The sent message this email answers.

        By its thread headers first: our Message-IDs are unique, so this finds exactly one message in one
        workspace. Failing that, by the sender, but only when the sender is authenticated (a From address is easy
        to forge) and only when exactly one workspace wrote to that address; otherwise the email is skipped."""
        with self._sessions() as session:
            if incoming.in_reply_to:
                row = session.scalar(select(Outreach).where(Outreach.message_id.in_(incoming.in_reply_to))
                                     .order_by(Outreach.id.desc()).limit(1))
                if row is not None:
                    return row
            sender = single_address(incoming.from_address)
            if not sender or not incoming.authenticated:
                return None
            since = utcnow() - timedelta(days=LOOKBACK_DAYS)
            rows = list(session.scalars(select(Outreach).where(
                func.lower(Outreach.to_address) == sender.lower(), Outreach.channel == "email",
                Outreach.sent_at >= since,
                or_(Outreach.status == "sent", Outreach.status == "replied", Outreach.status == "no_reply"),
            ).order_by(Outreach.sent_at.desc())))
            if len({r.workspace_id for r in rows}) != 1:
                return None  # nobody, or more than one workspace: never guess across workspaces
            return rows[0]

    @staticmethod
    def _move_lead(session, workspace_id: int, lead_id: str, intent: str, actor: str) -> None:
        target = reply_lib.LEAD_STATUS.get(intent)
        state = session.get(LeadState, (workspace_id, lead_id)) or LeadState(workspace_id=workspace_id,
                                                                             lead_id=lead_id)
        current = state.status or "new"
        if target and current not in ("won", "lost", "archived") and current != target:
            state.status, state.updated_by = target, actor
            pipeline.mark_status(session, workspace_id, lead_id, target, actor)
        elif current == "new":
            state.status, state.updated_by = "contacted", actor
        session.merge(state)

    def _draft_answer(self, session, workspace_id: int, original: Outreach, reply: Reply, profile, lead,
                      writer) -> int:
        knowledge = self._index_for(workspace_id).knowledge()
        evidence = tuple(knowledge.search(f"{reply.body}\n{lead_query(lead)}")) if knowledge.count() else ()
        # a confirmed reply is answered to whoever wrote it; anything else only ever to the person we wrote to
        to = reply.from_address if reply.verified and reply.from_address else original.to_address
        draft = reply_lib.draft_answer(profile, lead, original.body, reply.body, reply.intent, to,
                                       original.subject or lead.title, writer, evidence)
        has_docs = knowledge.count() > 0
        answer = Outreach(workspace_id=workspace_id, lead_id=original.lead_id, channel=draft.channel,
                          to_address=draft.to, subject=draft.subject, body=draft.body, source=draft.source,
                          kind="answer", run_id=original.run_id, created_by=AGENT_AUTHOR,
                          in_reply_to=reply.message_id,
                          evidence=evidence_out(evidence) if has_docs else None,
                          claims=claims_out(knowledge.check_claims(draft.body, evidence)) if has_docs else None)
        session.add(answer)
        session.flush()
        return answer.id


def fetch_recent(settings: Settings) -> list[Incoming]:
    """Recent mail in the reply folder, read without marking it as read."""
    since = (utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=IMAP_TIMEOUT) as imap:
        imap.login(settings.imap_user, settings.imap_password.get_secret_value())
        imap.select(settings.imap_folder, readonly=True)
        _status, data = imap.search(None, "SINCE", since)
        ids = (data[0] or b"").split()[-MAX_PER_POLL:]
        found = []
        for num in ids:
            _status, parts = imap.fetch(num, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                found.append(parse_email(raw, settings.imap_authserv_id))
        return found


def parse_email(raw: bytes, authserv_id: str | None = None) -> Incoming:
    message = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(message, EmailMessage)
    part = message.get_body(preferencelist=("plain",))
    try:
        body = part.get_content() if part is not None else ""
    except (LookupError, ValueError):
        body = ""
    threads = " ".join(str(message.get(h, "")) for h in ("In-Reply-To", "References")).split()
    sender = parseaddr(str(message.get("From", "")))[1] or None
    return Incoming(from_address=sender, authenticated=sender_authenticated(message, sender, authserv_id),
                    subject=str(message.get("Subject", ""))[:300], body=str(body)[:reply_lib.REPLY_MAX],
                    message_id=str(message.get("Message-ID", "")).strip() or None,
                    in_reply_to=tuple(t.strip() for t in threads if t.strip().startswith("<"))[:20])


def sender_authenticated(message: EmailMessage, sender: str | None, authserv_id: str | None) -> bool:
    """Whether OUR mail server confirmed the sender.

    Only the topmost Authentication-Results header is read: the receiving server adds it last, so it sits on top,
    and anything below could have been written by the sender. Its authserv-id must be the configured one. Then
    either the single DMARC result passed for exactly the From domain, or a DKIM result passed with a signing domain
    the From domain belongs to. Without a configured authserv-id nothing counts as confirmed."""
    if not authserv_id or not sender or "@" not in sender:
        return False
    headers = message.get_all("Authentication-Results") or []
    if not headers:
        return False
    parsed = parse_auth_results(str(headers[0]))
    if parsed is None or parsed[0] != authserv_id.lower():
        return False
    domain = sender.rsplit("@", 1)[1].lower().strip()
    results = parsed[1]
    dmarc = [r for r in results if r[0] == "dmarc"]
    if len(dmarc) == 1 and dmarc[0][1] == "pass" and dmarc[0][2].get("header.from") == domain:
        return True
    for method, result, props in results:
        if method == "dkim" and result == "pass":
            signer = props.get("header.d") or props.get("header.i", "").rsplit("@", 1)[-1]
            if "." in signer and (domain == signer or domain.endswith("." + signer)):
                return True
    return False


RESINFO = re.compile(r"^([a-z0-9][a-z0-9_-]*)\s*=\s*([a-z]+)$")
PROP = re.compile(r'^([a-z0-9_-]+\.[a-z0-9_-]+)\s*=\s*(.+)$')
TOKEN = re.compile(r'[^\s"=]+\s*=\s*"(?:[^"\\]|\\.)*"|[^\s"]+|"(?:[^"\\]|\\.)*"')


def parse_auth_results(header: str) -> tuple[str, list[tuple[str, str, dict[str, str]]]] | None:
    """RFC 8601: 'authserv-id [version]; method=result [reason="..."] [ptype.prop=value ...]; ...'.

    (Comments), nested or not, are removed first; quoted strings are kept whole, so text inside a comment or a
    quoted reason can never become a result or a property. Returns None if the header is malformed."""
    text = _without_comments(header.lower())
    if text is None:
        return None
    parts = _split_outside_quotes(text, ";")
    server_tokens = parts[0].split() if parts else []
    if not server_tokens:
        return None
    results = []
    for part in parts[1:]:
        tokens = TOKEN.findall(part.strip())
        if not tokens:
            continue
        head = RESINFO.match(tokens[0].replace(" ", ""))
        if head is None:
            continue
        props = {}
        for token in tokens[1:]:
            prop = PROP.match(token)
            if prop:
                props[prop.group(1)] = prop.group(2).strip().strip('"').lstrip("@")
        results.append((head.group(1), head.group(2), props))
    return server_tokens[0], results


def _without_comments(text: str) -> str | None:
    out, depth, quoted, escaped = [], 0, False, False
    for ch in text:
        if escaped:
            escaped = False
            if depth == 0:
                out.append(ch)
            continue
        if ch == "\\":
            escaped = True
            if depth == 0:
                out.append(ch)
            continue
        if quoted:
            out.append(ch)
            quoted = ch != '"'
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return None  # unbalanced: do not guess
            depth -= 1
        elif depth == 0:
            out.append(ch)
            quoted = ch == '"'
    return None if depth or quoted else "".join(out)


def _split_outside_quotes(text: str, sep: str) -> list[str]:
    parts, current, quoted = [], [], False
    for ch in text:
        if ch == '"':
            quoted = not quoted
        if ch == sep and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts
