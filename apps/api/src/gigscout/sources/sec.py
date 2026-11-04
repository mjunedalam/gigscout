"""US companies that just raised money: SEC Form D filings, from EDGAR's official daily index.

A company that has just raised a round often needs to build or grow its product, which makes it worth a call:
a buying signal, not a request for work. The SEC asks automated clients to name a contact in the User-Agent and stay
under ten requests a second (we make one a second), so this source is on only when GIGSCOUT_SEC_CONTACT_EMAIL is set.

Investment funds and real-estate vehicles file Form D too; they are left out. People named in filings are not kept.
"""

import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

import httpx
from defusedxml import ElementTree

from gigscout.http import PoliteClient
from gigscout.models import Client, Lead

INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/form.{day:%Y%m%d}.idx"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/primary_doc.xml"
FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/"
INDEX_DAYS = 3  # the latest business days with an index
LOOKBACK_DAYS = 8
MAX_FILINGS = 20  # filing documents read per run, newest first
FUND_NAME = re.compile(
    r"\b(fund|l\.?p\.?|lp|partners|capital|investors?|holdings?|trust|reit|series|ventures?|spv|portfolio|"
    r"opportunit(y|ies)|properties|realty|apartments|co-?invest)\b", re.I)
SKIPPED_INDUSTRIES = ("pooled investment fund", "reits", "real estate", "commercial banking", "investing")


class SecFormDSource:
    name = "sec_form_d"

    def __init__(self, client: PoliteClient, contact_email: str, today: Callable[[], date] | None = None) -> None:
        self._client = client
        self._headers = {"User-Agent": f"GigScout {contact_email}"}
        self._today = today or (lambda: datetime.now(UTC).date())
        self._seen: dict[str, Lead | None] = {}  # accession -> lead (None: skipped), so a filing is read once

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        """Recent filings, whatever the query: the agents' semantic search decides which fit the company."""
        leads: list[Lead] = []
        for cik, folder, accession, name, filed in self._recent_filings()[:min(limit, MAX_FILINGS)]:
            if accession not in self._seen:
                self._seen[accession] = self._read(cik, folder, accession, name, filed)
            if self._seen[accession] is not None:
                leads.append(self._seen[accession])
        return leads

    def _recent_filings(self) -> list[tuple[str, str, str, str, date]]:
        filings, days_found = [], 0
        for back in range(LOOKBACK_DAYS):
            day = self._today() - timedelta(days=back)
            if day.weekday() >= 5:
                continue
            try:
                text = self._client.get(INDEX_URL.format(year=day.year, quarter=(day.month - 1) // 3 + 1, day=day),
                                        headers=self._headers).text
            except httpx.HTTPStatusError:  # holidays and today's not-yet-published index
                continue
            filings.extend(parse_index(text, day))
            days_found += 1
            if days_found == INDEX_DAYS:
                break
        return filings

    def _read(self, cik: str, folder: str, accession: str, name: str, filed: date) -> Lead | None:
        xml = self._client.get(DOC_URL.format(cik=cik, folder=folder), headers=self._headers).text
        return parse_filing(xml, cik, folder, accession, name, filed)


def parse_index(text: str, day: date) -> list[tuple[str, str, str, str, date]]:
    """Original Form D filings (not amendments) by operating companies: (cik, folder, accession, name, day)."""
    out = []
    for line in text.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5 or parts[0] != "D":
            continue
        name, cik, path = parts[1], parts[2], parts[4]
        if FUND_NAME.search(name):
            continue
        accession = path.rsplit("/", 1)[-1].removesuffix(".txt")
        out.append((cik, accession.replace("-", ""), accession, name, day))
    return out


def parse_filing(xml: str, cik: str, folder: str, accession: str, name: str, filed: date) -> Lead | None:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return None

    def text(tag: str) -> str:
        node = root.find(f".//{tag}")
        return (node.text or "").strip() if node is not None and node.text else ""

    industry = text("industryGroupType")
    if not industry or any(skip in industry.lower() for skip in SKIPPED_INDUSTRIES):
        return None
    entity = text("entityName").title() if text("entityName").isupper() else (text("entityName") or name)
    offering, sold = _amount(text("totalOfferingAmount")), _amount(text("totalAmountSold"))
    city = text("city").title()
    state = text("stateOrCountryDescription").title()
    raised = f"raised {_money(sold)}" if sold else f"is raising {_money(offering)}" if offering else "is raising"
    lines = [
        f"{entity} filed a Form D with the SEC on {filed:%d %b %Y}: it {raised}"
        + (f" of a {_money(offering)} round" if sold and offering and offering != sold else "") + ".",
        f"Industry: {industry}.",
        f"Based in {', '.join(p for p in (city, state) if p)}." if city or state else "",
        f"Revenue: {text('revenueRange')}." if text("revenueRange") else "",
        "A company that has just raised money often needs to build, scale or modernise its product and systems.",
    ]
    return Lead(
        id=f"sec_form_d:{accession}",
        source="sec_form_d",
        title=f"{entity} {raised} ({industry})",
        description="\n".join(line for line in lines if line),
        url=FILING_URL.format(cik=cik, folder=folder),
        kind="signal",
        skills=(industry,),
        posted_at=datetime(filed.year, filed.month, filed.day, tzinfo=UTC),
        client=Client(name=entity[:120], country="United States"),
    )


def _amount(value: str) -> int | None:
    try:
        return int(float(value)) or None
    except ValueError:
        return None  # "Indefinite"


def _money(value: int | None) -> str:
    if not value:
        return "an undisclosed amount"
    return f"${value / 1_000_000:.1f}M" if value >= 1_000_000 else f"${value:,}"
