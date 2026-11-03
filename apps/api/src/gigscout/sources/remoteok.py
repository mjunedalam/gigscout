"""Remote OK — public JSON API. Their terms require linking back to the original URL and naming Remote OK.

Every listing is a company hiring a developer: a `hiring` signal the agency can pitch outsourcing to.
"""

from collections.abc import Sequence
from datetime import datetime

from gigscout.http import PoliteClient
from gigscout.models import Budget, Client, Lead
from gigscout.text import html_to_text, matches_any_query

API_URL = "https://remoteok.com/api"


class RemoteOkSource:
    name = "remoteok"

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        rows = self._client.get_json(API_URL)
        leads = (parse(row) for row in rows if isinstance(row, dict) and "id" in row)
        relevant = [lead for lead in leads if matches_any_query(lead.document(), queries)]
        return relevant[: limit * max(len(queries), 1)]


def parse(raw: dict) -> Lead:
    salary_min, salary_max = raw.get("salary_min") or None, raw.get("salary_max") or None
    return Lead(
        id=f"remoteok:{raw['id']}",
        source="remoteok",
        title=raw.get("position", "").strip(),
        description=html_to_text(raw.get("description")),
        url=raw.get("url") or f"https://remoteok.com/remote-jobs/{raw.get('slug', raw['id'])}",
        kind="hiring",
        skills=tuple(raw.get("tags") or ()),
        budget=Budget(minimum=salary_min, maximum=salary_max, currency="USD", kind="salary")
        if salary_min or salary_max
        else None,
        posted_at=datetime.fromisoformat(raw["date"]) if raw.get("date") else None,
        client=Client(name=raw["company"]) if raw.get("company") else None,
    )
