"""Public-sector tenders: UK Contracts Finder and Find a Tender (OCDS open data), EU TED, and US SAM.gov.

All official open-data APIs. Contracts Finder, TED and SAM.gov search by keyword; Find a Tender has no keyword
search, so its recent notices are read once and matched to the run's queries here. Closed tenders are skipped.
SAM.gov needs a free API key from api.data.gov (GIGSCOUT_SAM_GOV_API_KEY); the others need nothing.
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from gigscout.http import PoliteClient
from gigscout.models import Budget, Client, Lead
from gigscout.text import html_to_text, matches_any_query

LOOKBACK_DAYS = 14
# Rough rates, only so tender budgets can be compared with the profile's minimum. Not for quoting.
APPROX_USD = {"USD": 1.0, "GBP": 1.27, "EUR": 1.08}
Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:  # TED dates look like 2026-11-26+02:00
            parsed = datetime.fromisoformat(value[:10])
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _closed(deadline: datetime | None, now: datetime) -> bool:
    return deadline is not None and deadline < now


def _budget(amount, currency: str | None) -> Budget | None:
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    code = (currency or "").upper() or None
    return Budget(maximum=value, currency=code, usd_rate=APPROX_USD.get(code or ""), kind="fixed")


def _describe(text: str, deadline: datetime | None, category: str | None) -> str:
    header = [f"Deadline: {deadline:%d %b %Y}" if deadline else "", f"Category: {category}" if category else ""]
    return "\n".join([*(h for h in header if h), "", text]).strip()


def parse_ocds(source: str, release: dict, url: str, now: datetime) -> Lead | None:
    tender = release.get("tender") or {}
    title = (tender.get("title") or "").strip()
    deadline = _parse_dt((tender.get("tenderPeriod") or {}).get("endDate"))
    if not title or _closed(deadline, now) or tender.get("status") not in (None, "active", "planned"):
        return None
    buyer = release.get("buyer") or {}
    country = next((
        (p.get("address") or {}).get("countryName") for p in release.get("parties") or []
        if "buyer" in (p.get("roles") or [])
    ), None)
    category = (tender.get("classification") or {}).get("description")
    value = tender.get("value") or {}
    return Lead(
        id=f"{source}:{release['ocid']}", source=source, title=title, url=url, kind="project",
        description=_describe(html_to_text(tender.get("description")), deadline, category),
        skills=(category,) if category else (), budget=_budget(value.get("amount"), value.get("currency")),
        posted_at=_parse_dt(release.get("date")),
        client=Client(name=buyer.get("name"), country=country or "United Kingdom") if buyer.get("name") else None,
    )


class ContractsFinderSource:
    """UK public contracts of all sizes (Crown Commercial Service's Contracts Finder)."""

    name = "contracts_finder"
    API = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
    NOTICE = "https://www.contractsfinder.service.gov.uk/Notice/"

    def __init__(self, client: PoliteClient, now: Clock = utcnow) -> None:
        self._client = client
        self._now = now

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        now = self._now()
        since = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        leads: list[Lead] = []
        for query in queries:
            payload = self._client.get_json(self.API, params={
                "keyword": query, "stages": "tender", "publishedFrom": since, "limit": min(limit, 100),
            })
            for release in payload.get("releases", []):
                notice_id = release.get("id", "").rsplit("-", 1)[0]  # "<notice id>-<release number>"
                if lead := parse_ocds(self.name, release, self.NOTICE + notice_id, now):
                    leads.append(lead)
        return leads


class FindTenderSource:
    """UK higher-value public contracts (Find a Tender). No keyword search: recent notices, matched here."""

    name = "find_a_tender"
    API = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
    NOTICE = "https://www.find-tender.service.gov.uk/Notice/"
    PAGE_SIZE = 100
    MAX_PAGES = 5  # newest notices first; older pages rarely add open tenders

    def __init__(self, client: PoliteClient, now: Clock = utcnow) -> None:
        self._client = client
        self._now = now

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        now = self._now()
        since = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        wanted = limit * max(len(queries), 1)
        payload = self._client.get_json(self.API, params={
            "stages": "tender", "updatedFrom": since, "limit": self.PAGE_SIZE,
        })
        leads: list[Lead] = []
        for page in range(1, self.MAX_PAGES + 1):
            for release in payload.get("releases", []):
                lead = parse_ocds(self.name, release, self.NOTICE + release.get("id", ""), now)
                if lead and matches_any_query(f"{lead.title} {lead.description}", queries):
                    leads.append(lead)
            next_page = (payload.get("links") or {}).get("next")
            if len(leads) >= wanted or not next_page or not next_page.startswith(self.API) or page == self.MAX_PAGES:
                break
            payload = self._client.get_json(next_page)
        return leads[:wanted]


def _text(value, language: str = "eng") -> str:
    """TED fields are {language: text or [text]}; prefer English, else the first language."""
    if isinstance(value, list):
        return _text(value[0], language) if value else ""
    if isinstance(value, dict):
        chosen = value.get(language) or next(iter(value.values()), "")
        return _text(chosen, language)
    return str(value or "")


class TedSource:
    """EU tenders (Tenders Electronic Daily, the EU Official Journal supplement): contract notices only."""

    name = "ted"
    API = "https://api.ted.europa.eu/v3/notices/search"
    NOTICE = "https://ted.europa.eu/en/notice/-/detail/"
    FIELDS = [
        "notice-title", "description-lot", "buyer-name", "buyer-country", "publication-date",
        "deadline-receipt-tender-date-lot", "estimated-value-lot", "estimated-value-cur-lot",
    ]

    def __init__(self, client: PoliteClient, now: Clock = utcnow) -> None:
        self._client = client
        self._now = now

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        now = self._now()
        since = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        leads: list[Lead] = []
        for query in queries:
            phrase = query.replace('"', " ").strip()
            payload = self._client.post_json(self.API, {
                "query": f'FT~"{phrase}" AND PD>={since} AND notice-type IN (cn-standard cn-social)',
                "fields": self.FIELDS, "limit": min(limit, 100),
            })
            leads.extend(lead for n in payload.get("notices", []) if (lead := parse_ted(n, now)))
        return leads


def parse_ted(notice: dict, now: datetime) -> Lead | None:
    number = notice.get("publication-number")
    title = _text(notice.get("notice-title")).strip()
    deadline = _parse_dt(_text(notice.get("deadline-receipt-tender-date-lot")))
    if not number or not title or _closed(deadline, now):
        return None
    buyer = _text(notice.get("buyer-name")) or None
    country = _text(notice.get("buyer-country") or notice.get("organisation-country-buyer")) or None
    return Lead(
        id=f"ted:{number}", source="ted", title=title, url=TedSource.NOTICE + number, kind="project",
        description=_describe(_text(notice.get("description-lot")), deadline, None),
        budget=_budget(_text(notice.get("estimated-value-lot")), _text(notice.get("estimated-value-cur-lot"))),
        posted_at=_parse_dt(_text(notice.get("publication-date"))),
        client=Client(name=buyer, country=country) if buyer or country else None,
    )


class SamGovSource:
    """US federal opportunities (SAM.gov): solicitations and combined synopses, by title keyword."""

    name = "sam_gov"
    API = "https://api.sam.gov/opportunities/v2/search"
    NOTICE_TYPES = "o,k"  # solicitation, combined synopsis/solicitation

    def __init__(self, client: PoliteClient, api_key: str, now: Clock = utcnow) -> None:
        self._client = client
        self._now = now
        self._headers = {"X-Api-Key": api_key}  # a header, so the key never lands in request logs

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        now = self._now()
        window = {"postedFrom": f"{now - timedelta(days=LOOKBACK_DAYS):%m/%d/%Y}", "postedTo": f"{now:%m/%d/%Y}"}
        leads: list[Lead] = []
        for query in queries:
            payload = self._client.get_json(self.API, headers=self._headers, params={
                **window, "title": query, "ptype": self.NOTICE_TYPES, "limit": min(limit, 100),
            })
            leads.extend(lead for o in payload.get("opportunitiesData", []) if (lead := parse_sam(o, now)))
        return leads


def parse_sam(raw: dict, now: datetime) -> Lead | None:
    deadline = _parse_dt(raw.get("responseDeadLine"))
    title = (raw.get("title") or "").strip()
    if not raw.get("noticeId") or not title or _closed(deadline, now) or raw.get("active") == "No":
        return None
    agency = (raw.get("fullParentPathName") or "").split(".")[0] or None
    category = raw.get("naicsCode")
    award = (raw.get("award") or {}).get("amount")
    return Lead(
        id=f"sam_gov:{raw['noticeId']}", source="sam_gov", title=title, kind="project",
        url=raw.get("uiLink") or f"https://sam.gov/opp/{raw['noticeId']}/view",
        description=_describe(f"{raw.get('type', '')} · solicitation {raw.get('solicitationNumber', '')}".strip(" ·"),
                              deadline, f"NAICS {category}" if category else None),
        budget=_budget(award, "USD"), posted_at=_parse_dt(raw.get("postedDate")),
        client=Client(name=agency, country="United States") if agency else None,
    )
