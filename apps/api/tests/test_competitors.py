"""Competitor watch: public contract awards won by the companies a workspace competes with."""

from datetime import UTC, datetime

import httpx
import respx

from gigscout import competitors
from gigscout.http import PoliteClient
from tests.conftest import MEMBER_EMAIL, login

RELEASES = {"releases": [
    {"id": "104863-2026", "date": "2026-11-04T16:24:41Z", "tender": {"title": "Income Management Solution"},
     "buyer": {"name": "North Lincolnshire Council"},
     "awards": [{"date": "2026-11-03T00:00:00Z", "suppliers": [{"name": "Access Paysuite Limited"}],
                 "value": {"amount": 250000, "currency": "GBP"}}]},
    {"id": "104883-2026", "date": "2026-11-04T16:45:34Z", "tender": {"title": "Ecology Surveys"},
     "buyer": {"name": "Historic Environment Scotland"}, "awards": [{"suppliers": []}],
     "parties": [{"name": "Echoes Ecology Ltd", "roles": ["supplier"]}],
     "contracts": [{"value": {"amount": 40000, "currency": "GBP"}}]},
    {"id": "104898-2026", "tender": {"title": "No winner yet"}, "awards": [{"suppliers": []}]},
], "links": {}}


def test_names_match_without_legal_endings_and_only_on_every_word():
    assert competitors.matches("Access Paysuite Limited", "Access Paysuite Ltd")
    assert competitors.matches("ACCESS PAYSUITE (UK) LTD", "access paysuite")
    assert not competitors.matches("Access Systems Ltd", "Access Paysuite")
    assert not competitors.matches("Anything Ltd", "Ltd")  # nothing left to match on


@respx.mock
def test_award_notices_are_read_with_winners_values_and_dates(settings):
    respx.get(url__regex=r".*/robots\.txt$").mock(return_value=httpx.Response(404))
    respx.get(competitors.AWARDS_API).mock(return_value=httpx.Response(200, json=RELEASES))
    awards = competitors.recent_awards(PoliteClient(settings), now=datetime(2026, 11, 5, tzinfo=UTC))
    assert [a.suppliers for a in awards] == [("Access Paysuite Limited",), ("Echoes Ecology Ltd",)]
    first, second = awards
    assert (first.amount, first.currency, first.buyer) == (250000, "GBP", "North Lincolnshire Council")
    assert first.awarded_at == datetime(2026, 11, 3, tzinfo=UTC) and first.url.endswith("/104863-2026")
    assert second.amount == 40000  # from the contract when the award has no value


def test_admins_watch_competitors_and_wins_are_recorded_once(web):
    client, platform = web()
    awards = [a for r in RELEASES["releases"] if (a := competitors.parse_award(r))]
    platform.competitors._fetch = lambda: awards
    events = []
    platform.bus.publish = lambda type_, data=None, workspace_id=None: events.append(type_)
    login(client)
    assert client.post("/api/competitors", json={"name": "Access Paysuite"}).status_code == 201
    assert client.post("/api/competitors", json={"name": "Access  Paysuite"}).status_code == 409

    assert client.post("/api/competitors/check").json() == {"notices": 2, "new": 1}
    assert client.post("/api/competitors/check").json() == {"notices": 2, "new": 0}  # once
    [win] = client.get("/api/competitors/wins").json()
    assert win["competitor"] == "Access Paysuite" and win["buyer"] == "North Lincolnshire Council"
    assert win["amount"] == 250000 and win["title"] == "Income Management Solution"
    assert client.get("/api/competitors").json()[0]["wins"] == 1 and events.count("competitor.won") == 1

    login(client, MEMBER_EMAIL)  # members see wins but do not edit the list
    assert client.get("/api/competitors/wins").status_code == 200
    assert client.post("/api/competitors", json={"name": "Someone"}).status_code == 403
