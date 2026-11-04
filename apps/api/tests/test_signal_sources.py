# ruff: noqa: E501 - the EDGAR index fixture keeps its real fixed-width lines
"""Buying-signal sources: Hacker News 'Who is hiring?' and SEC Form D funding filings."""

from datetime import date

import httpx
import pytest
import respx

from gigscout.http import PoliteClient
from gigscout.sources import hackernews, sec
from gigscout.sources.hackernews import HackerNewsHiringSource
from gigscout.sources.sec import SecFormDSource

THREADS = {"hits": [
    {"objectID": "500", "title": "Ask HN: Who wants to be hired? (November 2026)"},
    {"objectID": "501", "title": "Ask HN: Who is hiring? (November 2026)"},
]}
COMMENTS = {"hits": [
    {"objectID": "9001", "parent_id": 501, "created_at_i": 1793520012,
     "comment_text": "Acme Health | Senior Django Engineer | Remote (US) | Full-time<p>We build clinic software."},
    {"objectID": "9002", "parent_id": 501, "created_at_i": 1793520012,
     "comment_text": "Beta Labs | Contract React developer | London<p>Three months to start."},
    {"objectID": "9003", "parent_id": 9001, "created_at_i": 1793520012,  # a reply, not a company post
     "comment_text": "Is this role open to EU?"},
    {"objectID": "9004", "parent_id": 501, "created_at_i": 1793520012,  # someone looking for work
     "comment_text": "Location: Spain<p>Remote: Yes<p>Willing to relocate: No<p>Technologies: Python"},
]}

INDEX = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------
D                Newcoda, Inc.                                                 2162347     20261103    edgar/data/2162347/0002162347-26-000001.txt
D                1789 Capital Cobra LP                                         2163308     20261103    edgar/data/2163308/0002163308-26-000001.txt
D/A              Oldco Inc.                                                    1000001     20261103    edgar/data/1000001/0001000001-26-000009.txt
D                Harbor Bank Corp                                              2160000     20261103    edgar/data/2160000/0002160000-26-000001.txt
"""
FORM_D = """<?xml version="1.0"?><edgarSubmission><primaryIssuer><entityName>NEWCODA, INC.</entityName>
<issuerAddress><city>MIAMI</city><stateOrCountryDescription>FLORIDA</stateOrCountryDescription></issuerAddress>
</primaryIssuer><offeringData><industryGroup><industryGroupType>Other Technology</industryGroupType></industryGroup>
<issuerSize><revenueRange>Decline to Disclose</revenueRange></issuerSize>
<offeringSalesAmounts><totalOfferingAmount>1800000</totalOfferingAmount><totalAmountSold>1265000</totalAmountSold>
</offeringSalesAmounts></offeringData><relatedPersonsList><relatedPersonInfo><relatedPersonName>
<firstName>Jane</firstName><lastName>Founder</lastName></relatedPersonName></relatedPersonInfo></relatedPersonsList>
</edgarSubmission>"""
BANK = FORM_D.replace("Other Technology", "Commercial Banking").replace("NEWCODA, INC.", "HARBOR BANK CORP")


@pytest.fixture
def client(settings):
    return PoliteClient(settings.model_copy(update={"http_min_interval": 0}))


@respx.mock
def test_hn_hiring_posts_become_hiring_and_contract_leads(client):
    respx.get(url__regex=r".*/robots\.txt$").mock(return_value=httpx.Response(404))
    respx.get(f"{hackernews.API}/search_by_date").mock(return_value=httpx.Response(200, json=THREADS))
    search = respx.get(f"{hackernews.API}/search").mock(return_value=httpx.Response(200, json=COMMENTS))

    leads = HackerNewsHiringSource(client).fetch(["django"], limit=20)

    assert search.calls[0].request.url.params["tags"] == "comment,story_501"  # the hiring thread, not the other
    assert [lead.id for lead in leads] == ["hn_hiring:9001", "hn_hiring:9002"]  # replies are left out
    first, second = leads
    assert first.kind == "hiring" and first.client.name == "Acme Health"
    assert first.title.startswith("Acme Health | Senior Django Engineer") and "clinic software" in first.description
    assert first.url == "https://news.ycombinator.com/item?id=9001"
    assert second.kind == "contract"


@respx.mock
def test_form_d_filings_become_funding_signals_without_funds_banks_or_people(client):
    respx.get(url__regex=r".*/robots\.txt$").mock(return_value=httpx.Response(404))
    index = respx.get(url__regex=r".*/daily-index/2026/QTR4/form\.\d{8}\.idx$")
    index.side_effect = lambda request: (httpx.Response(200, text=INDEX) if request.url.path.endswith("20261103.idx")
                                         else httpx.Response(404))
    newcoda = respx.get("https://www.sec.gov/Archives/edgar/data/2162347/000216234726000001/primary_doc.xml").mock(
        return_value=httpx.Response(200, text=FORM_D))
    respx.get("https://www.sec.gov/Archives/edgar/data/2160000/000216000026000001/primary_doc.xml").mock(
        return_value=httpx.Response(200, text=BANK))
    source = SecFormDSource(client, "ops@acme.com", today=lambda: date(2026, 11, 4))

    [lead] = source.fetch(["anything"], limit=10)

    assert lead.id == "sec_form_d:0002162347-26-000001" and lead.kind == "signal"
    assert lead.title == "Newcoda, Inc. raised $1.3M (Other Technology)"
    assert "of a $1.8M round" in lead.description and "Miami, Florida" in lead.description
    assert "Jane" not in lead.description and "Founder" not in lead.description  # people are not kept
    assert lead.client.name == "Newcoda, Inc." and lead.client.country == "United States"
    assert newcoda.calls[0].request.headers["user-agent"] == "GigScout ops@acme.com"  # SEC fair-access rule

    source.fetch(["again"], limit=10)
    assert newcoda.call_count == 1  # a filing is read once


def test_index_parsing_skips_amendments_and_investment_vehicles():
    rows = sec.parse_index(INDEX, date(2026, 11, 3))
    assert [name for _, _, _, name, _ in rows] == ["Newcoda, Inc.", "Harbor Bank Corp"]
    assert rows[0][1] == "000216234726000001" and rows[0][2] == "0002162347-26-000001"


def test_a_malformed_filing_is_skipped():
    assert sec.parse_filing("<not xml", "1", "2", "3", "X", date(2026, 11, 3)) is None
