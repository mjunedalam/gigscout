"""Any website as a lead source: the admin gives a name and a URL; we use the site's feed if it has one, else read
listing-style links from the page.

These URLs come from people, and the server fetches them, so every address (and every redirect hop) must be a
public web address: no other schemes, no credentials, nothing that resolves to a private, loopback, link-local or
otherwise internal IP. Robots.txt is respected through the polite client like for every other source.
"""

import hashlib
import ipaddress
import re
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
from bs4 import BeautifulSoup, Tag

from gigscout.http import PoliteClient
from gigscout.models import Lead
from gigscout.sources.rss import RssSource
from gigscout.text import html_to_text, matches_any_query

Resolver = Callable[[str], list[str]]
SiteKind = Literal["feed", "page"]

MAX_REDIRECTS = 5
TITLE_MIN, TITLE_MAX, TITLE_MIN_WORDS = 20, 160, 3  # link text that reads like a posting, not navigation
DESCRIPTION_CHARS = 600
FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json")
CONTAINERS = ("li", "article", "tr", "section", "div")


class UnsafeUrl(ValueError):
    """The address is not a public web address we are willing to fetch."""


def default_resolve(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except (socket.gaierror, UnicodeError):
        return []


def check_url(url: str, resolve: Resolver = default_resolve) -> str:
    """Return the URL normalised if it is a public http(s) address; raise UnsafeUrl otherwise."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeUrl("Use a full web address starting with http:// or https://")
    if parts.username or parts.password:
        raise UnsafeUrl("Web addresses with a username or password are not supported")
    host = parts.hostname.lower()
    addresses = resolve(host)
    if not addresses:
        raise UnsafeUrl(f"Could not find {host}")
    if not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise UnsafeUrl(f"{host} is not a public website")
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "site"


def fetch_public(client: PoliteClient, url: str, resolve: Resolver = default_resolve) -> tuple[str, str]:
    """GET a public URL, vetting each redirect before following it. Returns (final_url, body)."""
    current = check_url(url, resolve)
    for _ in range(MAX_REDIRECTS + 1):
        response = client.get(current, follow_redirects=False)
        if not response.is_redirect:
            return current, response.text
        current = check_url(urljoin(current, response.headers.get("location", "")), resolve)
    raise UnsafeUrl("The website redirected too many times")


@dataclass(frozen=True)
class SiteProbe:
    kind: SiteKind
    feed_url: str | None
    title: str
    url: str = ""  # the address as checked and normalised


def probe(client: PoliteClient, url: str, resolve: Resolver = default_resolve) -> SiteProbe:
    """Check we may read a site (robots.txt, public address) and decide how: its feed if it has one, else the page.

    Raises DisallowedByRobots, UnsafeUrl, or httpx errors for the caller to report.
    """
    start = check_url(url, resolve)
    final, body = fetch_public(client, start, resolve)
    parsed = feedparser.parse(body)
    if parsed.entries:
        return SiteProbe("feed", final, parsed.feed.get("title", "") or urlsplit(final).hostname or "", start)
    soup = BeautifulSoup(body, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else urlsplit(final).hostname or ""
    feeds = [urljoin(final, str(link["href"])) for link in soup.find_all("link", rel="alternate", href=True)
             if isinstance(link, Tag) and link.get("type") in FEED_TYPES]
    if feeds:
        best = max(feeds, key=lambda feed: _feed_relevance(final, feed))  # max keeps the first on a tie
        return SiteProbe("feed", check_url(best, resolve), title, start)
    return SiteProbe("page", None, title, start)


def _feed_relevance(page: str, feed: str) -> int:
    """Sites advertise many feeds (blog, news, releases); prefer the one for the section the admin gave us."""
    p, f = urlsplit(page), urlsplit(feed)
    section = p.path.rstrip("/")
    score = 2 if f.hostname == p.hostname else 0
    if section and f.path.startswith(section + "/"):
        score += 3
    elif section and f.path.split("/")[1:2] == section.split("/")[1:2]:
        score += 1
    return score


class WebsiteSource:
    """A configured website. Leads are 'project' kind: someone is asking for work to be done."""

    def __init__(
        self, client: PoliteClient, name: str, url: str, kind: SiteKind, feed_url: str | None = None,
        resolve: Resolver = default_resolve,
    ) -> None:
        self._client = client
        self.name = name
        self.url = url
        self.kind = kind
        self._feed_url = feed_url or url
        self._resolve = resolve
        self._rss = RssSource(client, name, [self._feed_url], kind="project")

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        leads = self._from_feed() if self.kind == "feed" else self._from_page()
        matching = [lead for lead in leads if matches_any_query(lead.document(), queries)]
        return matching[: limit * max(len(queries), 1)]

    def preview(self, limit: int) -> list[Lead]:
        """Everything the site currently offers, unfiltered: what an admin wants to see when testing it."""
        return (self._from_feed() if self.kind == "feed" else self._from_page())[:limit]

    def _from_feed(self) -> list[Lead]:
        final, body = fetch_public(self._client, self._feed_url, self._resolve)
        return [self._rss.parse_entry(entry, final) for entry in feedparser.parse(body).entries]

    def _from_page(self) -> list[Lead]:
        final, body = fetch_public(self._client, self.url, self._resolve)
        soup = BeautifulSoup(body, "html.parser")
        seen: set[str] = set()
        leads: list[Lead] = []
        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            href = urljoin(final, str(anchor["href"])).split("#")[0]
            if not _looks_like_a_posting(title) or href in seen or href == final or not href.startswith("http"):
                continue
            seen.add(href)
            leads.append(Lead(
                id=f"{self.name}:{hashlib.sha1(href.encode()).hexdigest()[:16]}",
                source=self.name, title=title, description=_context(anchor, title), url=href, kind="project",
            ))
        return leads


def _looks_like_a_posting(text: str) -> bool:
    return TITLE_MIN <= len(text) <= TITLE_MAX and len(text.split()) >= TITLE_MIN_WORDS


def _context(anchor: Tag, title: str) -> str:
    """The text around a listing link (its list item, card or row), which usually holds the summary."""
    container = anchor.find_parent(CONTAINERS)
    text = html_to_text(str(container), limit=DESCRIPTION_CHARS + len(title)) if container else ""
    return text.replace(title, "", 1).strip()[:DESCRIPTION_CHARS] or title
