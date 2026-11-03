"""Public-sector tenders: UK Contracts Finder and Find a Tender, EU TED, US SAM.gov."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from gigscout.http import PoliteClient
from gigscout.sources.registry import build_sources
from gigscout.sources.tenders import (
    ContractsFinderSource,
    FindTenderSource,
    SamGovSource,
    TedSource,
    parse_sam,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def polite(settings) -> PoliteClient:
    return PoliteClient(settings.model_copy(update={"http_min_interval": 0}))


@respx.mock
def test_contracts_finder_open_tenders_become_project_leads(settings):
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    found = httpx.Response(200, json=fixture("contracts_finder.json"))
    route = respx.get(ContractsFinderSource.API).mock(return_value=found)

    leads = ContractsFinderSource(polite(settings), now=lambda: NOW).fetch(["research"], limit=10)

    assert route.calls[0].request.url.params["keyword"] == "research"
    first = leads[0]
    assert first.id == "contracts_finder:ocds-b5fd17-566bb982-934c-41bf-b478-f829a67c56f0"
    assert first.url == "https://www.contractsfinder.service.gov.uk/Notice/8d6ee322-4f9f-4343-af0a-9769ed660d8e"
    assert first.kind == "project" and first.client.name == "Gambling Commission"
    assert first.budget.maximum == 50000 and first.budget.currency == "GBP" and first.budget.max_usd > 50000
    assert first.description.startswith("Deadline: 03 Dec 2026")


@respx.mock
def test_closed_tenders_are_skipped(settings):
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    respx.get(ContractsFinderSource.API).mock(return_value=httpx.Response(200, json=fixture("contracts_finder.json")))
    after_first_deadline = datetime(2026, 11, 20, tzinfo=UTC)  # second notice closed on 10 Nov
    leads = ContractsFinderSource(polite(settings), now=lambda: after_first_deadline).fetch(["x"], limit=10)
    assert [lead.client.name for lead in leads] == ["Gambling Commission"]


@respx.mock
def test_find_a_tender_is_matched_to_the_queries_locally(settings):
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    respx.get(FindTenderSource.API).mock(return_value=httpx.Response(200, json=fixture("find_a_tender.json")))
    source = FindTenderSource(polite(settings), now=lambda: NOW)
    leads = source.fetch(["assessments"], limit=10)
    assert [lead.title for lead in leads] == ["PME Opportunity for NDP Assessments"]
    assert leads[0].url == "https://www.find-tender.service.gov.uk/Notice/104375-2026"
    assert source.fetch(["blockchain"], limit=10) == []


@respx.mock
def test_ted_searches_contract_notices_and_prefers_english(settings):
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    route = respx.post(TedSource.API).mock(return_value=httpx.Response(200, json=fixture("ted.json")))

    leads = TedSource(polite(settings), now=lambda: NOW).fetch(["software development"], limit=10)

    query = json.loads(route.calls[0].request.content)["query"]
    assert 'FT~"software development"' in query and "PD>=20261020" in query and "cn-standard" in query
    assert len(leads) == 1  # the second notice's deadline has passed
    lead = leads[0]
    assert lead.id == "ted:741138-2026" and lead.title.startswith("France – Educational software")
    assert lead.client.name == "AFNOR" and lead.client.country == "FRA"
    assert lead.budget.maximum == 120000 and lead.budget.currency == "EUR"
    assert lead.url == "https://ted.europa.eu/en/notice/-/detail/741138-2026"


SAM = {
    "noticeId": "abc123", "title": "Cloud migration support services", "solicitationNumber": "W91-26-R-0001",
    "fullParentPathName": "DEPT OF DEFENSE.DEPT OF THE ARMY", "postedDate": "2026-10-30",
    "responseDeadLine": "2026-11-25T17:00:00-05:00", "type": "Solicitation", "naicsCode": "541512",
    "uiLink": "https://sam.gov/opp/abc123/view", "active": "Yes",
}


@respx.mock
def test_sam_gov_sends_the_key_as_a_header_not_in_the_url(settings):
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    route = respx.get(url__startswith=SamGovSource.API).mock(
        return_value=httpx.Response(200, json={"opportunitiesData": [SAM]}))

    leads = SamGovSource(polite(settings), "secret-key", now=lambda: NOW).fetch(["cloud migration"], limit=5)

    request = route.calls[0].request
    assert request.headers["x-api-key"] == "secret-key" and "secret-key" not in str(request.url)
    assert request.url.params["title"] == "cloud migration" and request.url.params["postedFrom"] == "10/20/2026"
    assert leads[0].client.name == "DEPT OF DEFENSE" and leads[0].url == "https://sam.gov/opp/abc123/view"


def test_inactive_or_closed_sam_notices_are_skipped():
    assert parse_sam({**SAM, "active": "No"}, NOW) is None
    assert parse_sam({**SAM, "responseDeadLine": "2026-10-01T00:00:00-05:00"}, NOW) is None


def test_tenders_are_built_in_and_sam_gov_only_with_a_key(settings):
    from pydantic import SecretStr

    names = set(build_sources(settings, polite(settings)))
    assert {"contracts_finder", "find_a_tender", "ted"} <= names and "sam_gov" not in names
    keyed = settings.model_copy(update={"sam_gov_api_key": SecretStr("k")})
    assert "sam_gov" in build_sources(keyed, polite(keyed))


@respx.mock
def test_find_a_tender_reads_more_pages_until_it_has_matches(settings):
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    first = {"releases": [], "links": {"next": FindTenderSource.API + "?cursor=abc"}}
    route = respx.get(url__startswith=FindTenderSource.API).mock(side_effect=[
        httpx.Response(200, json=first), httpx.Response(200, json=fixture("find_a_tender.json")),
    ])
    leads = FindTenderSource(polite(settings), now=lambda: NOW).fetch(["assessments"], limit=10)
    assert route.call_count == 2 and route.calls[1].request.url.params["cursor"] == "abc" and len(leads) == 1


@respx.mock
def test_find_a_tender_never_follows_a_next_link_off_its_own_api(settings):
    respx.get(url__regex=r".*/robots\.txt").mock(return_value=httpx.Response(404))
    respx.get(url__startswith=FindTenderSource.API).mock(return_value=httpx.Response(
        200, json={"releases": [], "links": {"next": "https://evil.example/steal"}}))
    elsewhere = respx.get(url__startswith="https://evil.example").mock(return_value=httpx.Response(200, json={}))
    assert FindTenderSource(polite(settings), now=lambda: NOW).fetch(["x"], limit=5) == [] and not elsewhere.called
