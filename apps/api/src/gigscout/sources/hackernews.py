"""Hacker News "Who is hiring?" (monthly thread), through HN's public Algolia search API.

Each top-level comment is one company hiring. That is a hiring signal: a company short of engineers is a company
that may hire an agency. Posts conventionally open with "Company | Role | Location | ..." on the first line.
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime

from gigscout.http import PoliteClient
from gigscout.models import Client, Lead
from gigscout.text import html_to_text

API = "https://hn.algolia.com/api/v1"
THREAD_PREFIX = "ask hn: who is hiring"
ITEM_URL = "https://news.ycombinator.com/item?id={id}"
TITLE_CHARS = 140
CONTRACT_HINT = re.compile(r"\b(contract|contractor|freelance|consultant|part[- ]time)\b", re.I)
# people looking for work sometimes post in the hiring thread with the "Who wants to be hired?" template
SEEKER = re.compile(r"^\s*location\s*:|willing to relocate\s*:|r[ée]sum[ée]/cv\s*:", re.I | re.M)


class HackerNewsHiringSource:
    name = "hn_hiring"

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        thread = self._latest_thread()
        if thread is None:
            return []
        leads: list[Lead] = []
        for query in queries:
            payload = self._client.get_json(f"{API}/search", params={
                "tags": f"comment,story_{thread}", "query": query, "hitsPerPage": limit,
            })
            leads.extend(lead for hit in payload.get("hits", [])
                         if str(hit.get("parent_id")) == thread and (lead := parse(hit)) is not None)
        return leads

    def _latest_thread(self) -> str | None:
        payload = self._client.get_json(f"{API}/search_by_date", params={
            "tags": "story,author_whoishiring", "hitsPerPage": 5,
        })
        for hit in payload.get("hits", []):
            if (hit.get("title") or "").lower().startswith(THREAD_PREFIX):
                return str(hit["objectID"])
        return None


def parse(hit: dict) -> Lead | None:
    text = html_to_text(hit.get("comment_text"))
    if not text.strip() or SEEKER.search(text):
        return None
    first_line = text.strip().splitlines()[0].strip()
    company = first_line.split("|", 1)[0].strip() if "|" in first_line else ""
    created = hit.get("created_at_i")
    return Lead(
        id=f"hn_hiring:{hit['objectID']}",
        source="hn_hiring",
        title=first_line[:TITLE_CHARS],
        description=text,
        url=ITEM_URL.format(id=hit["objectID"]),
        kind="contract" if CONTRACT_HINT.search(first_line) else "hiring",
        posted_at=datetime.fromtimestamp(created, UTC) if created else None,
        client=Client(name=company[:120]) if company else None,
    )
