"""Generic RSS/Atom source — the extension point for any board or tender portal that publishes a feed.

We Work Remotely is registered through this adapter; add more feeds with GIGSCOUT_RSS_FEEDS.
"""

import hashlib
from calendar import timegm
from collections.abc import Sequence
from datetime import UTC, datetime

import feedparser

from gigscout.http import PoliteClient
from gigscout.models import Lead, LeadKind
from gigscout.text import html_to_text, matches_any_query


class RssSource:
    def __init__(self, client: PoliteClient, name: str, feeds: Sequence[str], kind: LeadKind = "hiring") -> None:
        self._client = client
        self.name = name
        self._feeds = tuple(feeds)
        self._kind = kind

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        leads: list[Lead] = []
        for feed_url in self._feeds:
            parsed = feedparser.parse(self._client.get_text(feed_url))
            items = (self._parse(entry, feed_url) for entry in parsed.entries)
            leads.extend(lead for lead in items if matches_any_query(lead.document(), queries))
        return leads[: limit * max(len(queries), 1)]

    def _parse(self, entry, feed_url: str) -> Lead:
        link = entry.get("link") or feed_url
        native_id = entry.get("id") or link
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        return Lead(
            id=f"{self.name}:{hashlib.sha1(native_id.encode()).hexdigest()[:16]}",
            source=self.name,
            title=entry.get("title", "").strip(),
            description=html_to_text(entry.get("summary") or entry.get("description")),
            url=link,
            kind=self._kind,
            skills=tuple(t.get("term", "") for t in entry.get("tags", []) if t.get("term")),
            posted_at=datetime.fromtimestamp(timegm(published), UTC) if published else None,
        )
