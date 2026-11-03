"""Remotive — public JSON API. Their terms require linking back and naming Remotive as the source.

Contract and freelance roles become `contract` leads (staff augmentation); the rest are `hiring` signals.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from gigscout.http import PoliteClient
from gigscout.models import Client, Lead
from gigscout.text import html_to_text

API_URL = "https://remotive.com/api/remote-jobs"
CONTRACT_JOB_TYPES = {"freelance", "contract"}


class RemotiveSource:
    name = "remotive"

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        leads: list[Lead] = []
        for query in queries:
            payload = self._client.get_json(API_URL, params={"search": query, "limit": limit})
            leads.extend(parse(job) for job in payload.get("jobs", []))
        return leads


def parse(raw: dict) -> Lead:
    published = raw.get("publication_date")
    posted_at = datetime.fromisoformat(published) if published else None
    if posted_at and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    company = raw.get("company_name")
    return Lead(
        id=f"remotive:{raw['id']}",
        source="remotive",
        title=raw.get("title", "").strip(),
        description=html_to_text(raw.get("description")),
        url=raw["url"],
        kind="contract" if (raw.get("job_type") or "") in CONTRACT_JOB_TYPES else "hiring",
        skills=tuple(raw.get("tags") or ()),
        posted_at=posted_at,
        client=Client(name=company) if company else None,
    )
