"""Freelancer.com — public, unauthenticated 'active projects' endpoint of their official API.

Clients post projects here to outsource them, so every result is a `project` lead. The public endpoint hides
the client's identity, but exposes how many bids a project already has: our competition signal.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from gigscout.http import PoliteClient
from gigscout.models import Budget, Client, Lead
from gigscout.text import html_to_text

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
PROJECT_URL = "https://www.freelancer.com/projects/{seo_url}"


class FreelancerSource:
    name = "freelancer"

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        leads: list[Lead] = []
        for query in queries:
            params = {"query": query, "limit": limit, "full_description": "true", "job_details": "true"}
            payload = self._client.get_json(API_URL, params=params)
            leads.extend(parse(p) for p in payload.get("result", {}).get("projects", []))
        return leads


def parse(raw: dict) -> Lead:
    currency = raw.get("currency") or {}
    budget = raw.get("budget") or {}
    submitted = raw.get("time_submitted")
    country = ((raw.get("location") or {}).get("country") or {}).get("name")
    return Lead(
        id=f"freelancer:{raw['id']}",
        source="freelancer",
        title=raw.get("title", "").strip(),
        description=html_to_text(raw.get("description") or raw.get("preview_description")),
        url=PROJECT_URL.format(seo_url=raw.get("seo_url", raw["id"])),
        kind="project",
        skills=tuple(job["name"] for job in raw.get("jobs") or [] if job.get("name")),
        budget=Budget(
            minimum=budget.get("minimum"),
            maximum=budget.get("maximum"),
            currency=currency.get("code"),
            usd_rate=currency.get("exchange_rate"),
            kind="hourly" if raw.get("type") == "hourly" else "fixed",
        ),
        posted_at=datetime.fromtimestamp(submitted, UTC) if submitted else None,
        client=Client(country=country) if country else None,
        bid_count=(raw.get("bid_stats") or {}).get("bid_count"),
    )
