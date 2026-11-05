"""The research agent: before a pitch, learn who the client is from their own website and what the lead store
already knows about them, and turn it into a short brief with its sources.

Websites come from untrusted lead text, so they are fetched only through the public-address-only client, with
robots.txt respected, and page text is treated as information, never as instructions.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from gigscout.http import DisallowedByRobots, PoliteClient, TooLarge
from gigscout.mail import SHARED_MAIL_DOMAINS
from gigscout.models import AgencyProfile, Lead
from gigscout.sources.website import UnsafeUrl, fetch_public
from gigscout.store.vector_store import StoredLead
from gigscout.text import contains_term

log = logging.getLogger(__name__)

PAGE_CHARS = 5000
MAX_PAGE_BYTES = 2_000_000
MAX_RELATED = 6
EXTRA_PATHS = ("/about", "/about-us", "/company")
URL = re.compile(r"https?://[^\s)\]>\"'|,]+", re.IGNORECASE)
# where the lead was posted, not who posted it
NOT_THE_CLIENT = (
    "upwork.com", "freelancer.com", "fiverr.com", "peopleperhour.com", "guru.com", "toptal.com", "linkedin.com",
    "news.ycombinator.com", "ycombinator.com", "remoteok.com", "remotive.com", "weworkremotely.com", "indeed.com",
    "glassdoor.com", "github.com", "gitlab.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "medium.com", "google.com", "docs.google.com", "notion.so", "calendly.com", "sec.gov",
    "contractsfinder.service.gov.uk", "find-tender.service.gov.uk", "ted.europa.eu", "sam.gov", "python.org",
    "workable.com", "lever.co", "greenhouse.io", "ashbyhq.com", "wellfound.com", "angel.co",
)
TECH = {  # what a page's HTML gives away: name -> markers
    "React": ("react", "__next", "_next/static"), "Next.js": ("_next/static", "__next_data__"),
    "Vue": ("vue.js", "vue.min.js", "data-v-", "__nuxt"), "Nuxt": ("__nuxt", "_nuxt/"),
    "Angular": ("ng-version", "angular"), "WordPress": ("wp-content", "wp-includes"), "Shopify": ("cdn.shopify",),
    "Webflow": ("webflow",), "Wix": ("wixstatic", "wix.com"), "Squarespace": ("squarespace",),
    "HubSpot": ("hs-scripts", "hubspot"), "Intercom": ("intercom",), "Stripe": ("js.stripe.com",),
    "Segment": ("cdn.segment.com",), "Google Analytics": ("googletagmanager", "google-analytics"),
    "Salesforce": ("salesforce", "force.com"), "Zendesk": ("zendesk", "zdassets"), "Django": ("csrfmiddlewaretoken",),
    "Ruby on Rails": ("csrf-param", "rails-ujs"), "Laravel": ("laravel",), "Gatsby": ("___gatsby",),
}


class ResearchBrief(BaseModel):
    """What the team should know about a client before pitching."""

    summary: str = Field(description="2-3 sentences: who the client is and what they do", max_length=600)
    needs: list[str] = Field(default_factory=list, description="0-4 things they likely need, given the lead")
    signals: list[str] = Field(default_factory=list, description="0-4 facts that show timing or budget")
    talking_points: list[str] = Field(default_factory=list,
                                      description="1-3 specific angles for the first message, grounded in the sources")
    risks: list[str] = Field(default_factory=list, description="0-3 things to check or be careful about")


class Researcher(Protocol):
    def research(self, profile: AgencyProfile, lead: Lead, findings: str) -> ResearchBrief: ...


@dataclass
class Findings:
    website: str | None = None
    title: str = ""
    description: str = ""
    text: str = ""
    tech: list[str] = field(default_factory=list)
    related: list[StoredLead] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_prompt(self) -> str:
        parts = [f"Website: {self.website or 'not found'}"]
        if self.title or self.description:
            parts.append(f"Site title: {self.title}\nSite description: {self.description}")
        if self.tech:
            parts.append(f"Technology seen on the site: {', '.join(self.tech)}")
        if self.text:
            parts.append(f"Site text (from the client's own website):\n{self.text[:PAGE_CHARS]}")
        if self.related:
            lines = [f"- {r.lead.kind} from {r.lead.source}, {r.seen_at:%Y-%m-%d}: {r.lead.title}"
                     for r in self.related]
            parts.append("Other things seen about this client:\n" + "\n".join(lines))
        return "\n\n".join(parts)


def find_website(lead: Lead) -> str | None:
    """The client's own site: a link in the lead text that is not a marketplace, else a business email domain."""
    for match in URL.findall(f"{lead.description} {lead.title}"):
        parts = urlsplit(match)
        host = (parts.hostname or "").lower().removeprefix("www.")
        if host and "." in host and not _is_platform(host):
            port = f":{parts.port}" if parts.port else ""
            return f"{parts.scheme.lower()}://{host}{port}"
    host = (urlsplit(lead.url).hostname or "").lower().removeprefix("www.") if lead.url else ""
    if host and lead.kind == "inbound" and not _is_platform(host):
        return f"https://{host}"
    email = lead.client.email if lead.client else None
    if email and "@" in email:
        domain = email.rsplit("@", 1)[1].lower().strip()
        if domain not in SHARED_MAIL_DOMAINS and not _is_platform(domain):
            return f"https://{domain}"
    return None


def related_leads(lead: Lead, records: Sequence[StoredLead], website: str | None) -> list[StoredLead]:
    """Other leads about the same client (hiring posts, funding filings, earlier projects)."""
    name = (lead.client.name or "").strip() if lead.client else ""
    host = (urlsplit(website).hostname or "").removeprefix("www.") if website else ""
    hits = []
    for stored in records:
        other = stored.lead
        if other.id == lead.id:
            continue
        same_name = len(name) > 3 and other.client is not None and (other.client.name or "").lower() == name.lower()
        mentions = (host and host in f"{other.description} {other.url}".lower()) or (
            len(name) > 3 and contains_term(other.title, name))
        if same_name or mentions:
            hits.append(stored)
    return sorted(hits, key=lambda s: s.seen_at, reverse=True)[:MAX_RELATED]


def gather(client: PoliteClient, lead: Lead, records: Sequence[StoredLead]) -> Findings:
    found = Findings(website=find_website(lead))
    if found.website:
        for path in ("", *EXTRA_PATHS):
            url = urljoin(found.website, path) if path else found.website
            try:
                final, body = fetch_public(client, url, max_bytes=MAX_PAGE_BYTES)
            except (UnsafeUrl, DisallowedByRobots, TooLarge, httpx.HTTPError, ValueError) as exc:
                found.errors.append(f"{url}: {type(exc).__name__}")
                if not path:
                    break  # no homepage: the rest will not work either
                continue
            _read_page(found, final, body)
            if len(found.text) > PAGE_CHARS:
                break
    found.related = related_leads(lead, records, found.website)
    found.sources.extend({"label": f"{r.lead.source}: {r.lead.title[:80]}", "url": r.lead.url}
                         for r in found.related if _web_url(r.lead.url))
    return found


def rule_brief(lead: Lead, found: Findings) -> ResearchBrief:
    name = lead.client.name if lead.client and lead.client.name else "The client"
    summary = found.description or (found.text[:240] if found.text else "")
    summary = f"{name}: {summary}" if summary else f"{name} posted: {lead.title}."
    signals = [f"{r.lead.kind.title()} on {r.lead.source}: {r.lead.title[:100]}" for r in found.related[:3]]
    if lead.budget and lead.budget.max_usd:
        signals.insert(0, f"Budget up to ${lead.budget.max_usd:,.0f}")
    points = [f"Their site runs on {', '.join(found.tech[:3])}"] if found.tech else []
    risks = [] if found.website else ["No company website found: confirm who the client is"]
    return ResearchBrief(summary=summary[:600], needs=list(lead.skills[:4]), signals=signals[:4],
                         talking_points=points, risks=risks)


def brief_for(profile: AgencyProfile, lead: Lead, found: Findings, researcher: object | None) -> tuple[
        ResearchBrief, str]:
    if researcher is None or not hasattr(researcher, "research"):
        return rule_brief(lead, found), "rules"
    try:
        return researcher.research(profile, lead, found.as_prompt()), "ai"
    except Exception:
        log.warning("Research by the LLM failed for %s; using the facts found", lead.id, exc_info=True)
        return rule_brief(lead, found), "rules"


RESEARCH_CHARS = 800


def for_drafting(brief: dict | None) -> str:
    """The brief as the pitch writer gets it: kept apart from our own angle and marked untrusted by the prompt,
    without links, and short. It was written from the client's website, which anyone can put words on."""
    if not brief:
        return ""
    points = "; ".join(str(p) for p in (brief.get("talking_points") or [])[:3])
    text = f"{brief.get('summary', '')} Angles: {points}" if points else str(brief.get("summary", ""))
    return " ".join(URL.sub("", text).split())[:RESEARCH_CHARS]


def _read_page(found: Findings, url: str, body: bytes) -> None:
    html = body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    lowered = html.lower()
    for name, markers in TECH.items():
        if name not in found.tech and any(m in lowered for m in markers):
            found.tech.append(name)
    if not found.title and soup.title and soup.title.string:
        found.title = " ".join(soup.title.string.split())[:200]
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if not found.description and meta and meta.get("content"):
        found.description = " ".join(str(meta["content"]).split())[:400]
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    found.text = f"{found.text} {text}".strip()[:PAGE_CHARS * 2]
    found.sources.append({"label": found.title or url, "url": url})


def _web_url(url: str | None) -> bool:
    return bool(url) and urlsplit(url).scheme in ("http", "https")


def _is_platform(host: str) -> bool:
    return any(host == p or host.endswith("." + p) for p in NOT_THE_CLIENT)
