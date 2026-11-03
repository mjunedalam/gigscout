"""The daily digest: the best new leads since the last one, with a pitch each, sent by email and/or Slack.

Pure building blocks (build, render, send); scheduling and settings live in gigscout.platform.digests.
"""

import smtplib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from html import escape
from urllib.parse import urlsplit

import httpx

from gigscout.agent.nodes import budget_label
from gigscout.config import Settings
from gigscout.platform.tables import LeadState
from gigscout.store.vector_store import LeadIndex

DEFAULT_WINDOW = timedelta(hours=24)
SLACK_HOST = "hooks.slack.com"
SLACK_TIMEOUT = 10
SMTP_TIMEOUT = 20


class UnsafeWebhook(ValueError):
    """Not a Slack incoming-webhook URL (we only ever post to hooks.slack.com)."""


@dataclass(frozen=True)
class DigestSettingsView:
    min_score: float = 0.6
    max_leads: int = 10
    last_sent_at: datetime | None = None


@dataclass(frozen=True)
class DigestLead:
    id: str
    title: str
    url: str | None
    kind: str
    source: str
    budget: str
    score: float
    pitch: str
    reasons: str


@dataclass(frozen=True)
class Digest:
    leads: list[DigestLead]
    since: datetime
    generated_at: datetime


def build_digest(states: Iterable[LeadState], index: LeadIndex, config: DigestSettingsView, now: datetime) -> Digest:
    """Leads still 'new' in the pipeline, scored at least min_score, updated since the last digest (or 24h)."""
    since = _aware(config.last_sent_at) if config.last_sent_at else now - DEFAULT_WINDOW
    def eligible(s: LeadState) -> bool:  # status is None on rows not yet saved; the column defaults to "new"
        fresh_enough = s.updated_at is not None and _aware(s.updated_at) >= since
        return (s.status or "new") == "new" and s.score is not None and s.score >= config.min_score and fresh_enough

    fresh = sorted(filter(eligible, states), key=lambda s: s.score, reverse=True)
    leads: list[DigestLead] = []
    for state in fresh:
        lead = index.get(state.lead_id)
        if lead is None:
            continue
        leads.append(DigestLead(
            id=lead.id, title=lead.title, url=lead.url, kind=lead.kind, source=lead.source, budget=budget_label(lead),
            score=state.score, pitch=state.pitch, reasons=state.reasons,
        ))
        if len(leads) >= config.max_leads:
            break
    return Digest(leads=leads, since=since, generated_at=now)


def render_markdown(digest: Digest) -> str:
    if not digest.leads:
        return "No new qualified leads since the last digest. The agents keep looking."
    lines = [f"**{len(digest.leads)} new lead{'s' if len(digest.leads) != 1 else ''} worth your time**", ""]
    for i, lead in enumerate(digest.leads, 1):
        title = f"[{lead.title}]({lead.url})" if lead.url else lead.title
        lines.append(f"{i}. {title} · {lead.kind} · {lead.source} · {lead.budget} · score {lead.score:.2f}")
        if lead.reasons:
            lines.append(f"   Why: {lead.reasons}")
        if lead.pitch:
            lines.append(f"   Open with: “{lead.pitch}”")
    return "\n".join(lines)


def render_html(digest: Digest) -> str:
    if not digest.leads:
        return f"<p>{escape(render_markdown(digest))}</p>"
    items = []
    for lead in digest.leads:
        title = f'<a href="{escape(lead.url)}">{escape(lead.title)}</a>' if lead.url else escape(lead.title)
        meta = escape(f"{lead.kind} · {lead.source} · {lead.budget} · score {lead.score:.2f}")
        why = f"<br><span>Why: {escape(lead.reasons)}</span>" if lead.reasons else ""
        pitch = f"<br><em>Open with: “{escape(lead.pitch)}”</em>" if lead.pitch else ""
        body = f"<strong>{title}</strong><br><small>{meta}</small>{why}{pitch}"
        items.append(f"<li style='margin-bottom:12px'>{body}</li>")
    return (f"<h2 style='font-family:sans-serif'>{len(digest.leads)} new leads worth your time</h2>"
            f"<ol style='font-family:sans-serif;line-height:1.5'>{''.join(items)}</ol>")


def render_slack(digest: Digest) -> str:
    """Slack mrkdwn built from scratch: lead fields come from outside websites, so &, < and > are escaped (Slack's own
    rule) and links are only made from http(s) URLs. Otherwise a title like "<!channel>" would ping everyone."""
    if not digest.leads:
        return _slack_escape(render_markdown(digest))
    lines = [f"*{len(digest.leads)} new lead{'s' if len(digest.leads) != 1 else ''} worth your time*", ""]
    for i, lead in enumerate(digest.leads, 1):
        title = _slack_escape(lead.title)
        if lead.url and urlsplit(lead.url).scheme in ("http", "https"):
            title = f"<{_slack_escape(lead.url)}|{title.replace('|', '¦')}>"
        meta = _slack_escape(f"{lead.kind} · {lead.source} · {lead.budget} · score {lead.score:.2f}")
        lines.append(f"{i}. {title} · {meta}")
        if lead.reasons:
            lines.append(f"    Why: {_slack_escape(lead.reasons)}")
        if lead.pitch:
            lines.append(f"    Open with: “{_slack_escape(lead.pitch)}”")
    return "\n".join(lines)


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def check_slack_webhook(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.hostname != SLACK_HOST or not parts.path.startswith("/services/"):
        raise UnsafeWebhook("Use a Slack incoming-webhook URL: https://hooks.slack.com/services/…")
    return url.strip()


def send_slack(url: str, digest: Digest) -> None:
    response = httpx.post(check_slack_webhook(url), json={"text": render_slack(digest), "unfurl_links": False},
                          timeout=SLACK_TIMEOUT,
                          follow_redirects=False)
    response.raise_for_status()


def email_ready(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(settings: Settings, to: list[str], digest: Digest) -> None:
    message = EmailMessage()
    count = len(digest.leads)
    message["Subject"] = f"GigScout: {count} new lead{'s' if count != 1 else ''} worth your time"
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(to)
    message.set_content(render_markdown(digest))
    message.add_alternative(render_html(digest), subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
