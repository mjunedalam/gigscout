"""Competitor watch: public contracts your competitors won, from UK Find a Tender award notices (open data).

Marketplaces never show who bids, but public-sector awards name the winning supplier. A competitor matches a
supplier when every word of its name (legal endings such as Ltd or PLC aside) appears in the supplier's name.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from gigscout.http import PoliteClient

AWARDS_API = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
NOTICE_URL = "https://www.find-tender.service.gov.uk/Notice/"
LOOKBACK_DAYS = 30
PAGE_SIZE = 100
MAX_PAGES = 10
LEGAL_WORDS = {"ltd", "limited", "plc", "llp", "llc", "inc", "incorporated", "corp", "corporation", "co", "company",
               "group", "holdings", "uk", "the", "and"}
_WORD = re.compile(r"[a-z0-9]+")
_PLACEHOLDER = re.compile(r"^see\b|\bnotice for\b", re.I)  # "See Contracts Finder Notice for full supplier list"


@dataclass(frozen=True)
class Award:
    notice_id: str
    title: str
    buyer: str
    suppliers: tuple[str, ...]
    amount: float | None
    currency: str | None
    awarded_at: datetime | None
    url: str


def name_words(name: str) -> frozenset[str]:
    words = _WORD.findall(name.lower().replace("&", " and "))
    return frozenset(w for w in words if w not in LEGAL_WORDS)


def matches(supplier: str, competitor: str) -> bool:
    wanted = name_words(competitor)
    return bool(wanted) and wanted <= name_words(supplier)


def parse_award(release: dict) -> Award | None:
    awards = release.get("awards") or []
    suppliers = [s.get("name") for a in awards for s in a.get("suppliers") or []
                 if s.get("name") and not _PLACEHOLDER.search(s["name"])]
    if not suppliers:  # some notices list winners only as parties
        suppliers = [p.get("name") for p in release.get("parties") or []
                     if "supplier" in (p.get("roles") or []) and p.get("name")]
    if not suppliers:
        return None
    value = next((v for v in (
        *(a.get("value") for a in awards), *(c.get("value") for c in release.get("contracts") or []),
        (release.get("tender") or {}).get("value"),
    ) if v and v.get("amount")), {})
    when = next((a.get("date") for a in awards if a.get("date")), None) or release.get("date")
    return Award(
        notice_id=str(release.get("id") or release.get("ocid") or ""),
        title=((release.get("tender") or {}).get("title") or "").strip()[:300],
        buyer=((release.get("buyer") or {}).get("name") or "").strip()[:200],
        suppliers=tuple(dict.fromkeys(s.strip() for s in suppliers)),
        amount=float(value["amount"]) if value.get("amount") else None,
        currency=value.get("currency"),
        awarded_at=_parse(when),
        url=NOTICE_URL + str(release.get("id") or ""),
    )


def recent_awards(client: PoliteClient, now: datetime | None = None, days: int = LOOKBACK_DAYS) -> list[Award]:
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    payload = client.get_json(AWARDS_API, params={"stages": "award", "updatedFrom": since, "limit": PAGE_SIZE})
    awards: list[Award] = []
    for page in range(1, MAX_PAGES + 1):
        awards.extend(a for r in payload.get("releases", []) if (a := parse_award(r)) and a.notice_id)
        nxt = (payload.get("links") or {}).get("next")
        if not nxt or not nxt.startswith(AWARDS_API) or page == MAX_PAGES:
            break
        payload = client.get_json(nxt)
    return awards


def wins_for(awards: Sequence[Award], competitor: str) -> list[tuple[Award, str]]:
    """(award, the supplier name that matched) for each award this competitor won."""
    out = []
    for award in awards:
        supplier = next((s for s in award.suppliers if matches(s, competitor)), None)
        if supplier:
            out.append((award, supplier))
    return out


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


AwardFetcher = Callable[[], list[Award]]
