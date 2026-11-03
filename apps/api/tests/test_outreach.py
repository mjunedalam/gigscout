"""Outreach: a first message per lead (email or marketplace bid), sending it, tracking replies, and CRM sync."""

import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from gigscout.crm import CrmError, HubSpot, Pipedrive
from gigscout.models import AgencyProfile, Budget, Client
from gigscout.outreach import OutreachDraft, draft_outreach, template_draft
from gigscout.platform.tables import LeadState
from tests.conftest import ADMIN_EMAIL, FakeReasoner, login, make_lead


def stocked(web, **settings):
    """The app with the sample leads already found."""
    client, platform = web(**settings)
    platform.service.deps.index.add_new(platform.service.deps.sources["fake"].fetch([], 10))
    login(client)
    return client, platform

PROFILE = AgencyProfile(name="Bright Lane", company_type="Marketing agency", services=("SEO", "Paid ads"))


def test_inbound_leads_with_an_email_get_an_email_draft():
    lead = make_lead("1", "Need SEO for our bakery", kind="inbound", client=Client(name="Ana", email="ana@bakery.com"))
    draft = template_draft(PROFILE, lead, pitch="We grew 3 bakeries' traffic 2x.")
    assert draft.channel == "email" and draft.to == "ana@bakery.com"
    assert "Need SEO for our bakery" in draft.subject and "Bright Lane" in draft.body
    assert "We grew 3 bakeries' traffic 2x." in draft.body and "Ana" in draft.body and "{" not in draft.body


def test_marketplace_leads_get_bid_copy_and_hiring_leads_get_a_services_offer():
    bid = template_draft(PROFILE, make_lead("2", "Run our Google Ads"), pitch="")
    assert bid.channel == "bid" and bid.to is None and bid.subject == ""
    hiring = template_draft(PROFILE, make_lead("3", "Hiring: SEO specialist", kind="hiring"), pitch="")
    assert "instead of" in hiring.body.lower() or "rather than" in hiring.body.lower()


def test_the_llm_writes_the_draft_when_available_and_templates_cover_failures():
    lead = make_lead("1", "Need SEO", kind="inbound", client=Client(email="a@b.com"))
    written = draft_outreach(PROFILE, lead, "pitch", FakeReasoner())
    assert written.source == "ai" and written.body.startswith("AI draft") and written.to == "a@b.com"
    fallback = draft_outreach(PROFILE, lead, "pitch", FakeReasoner(fail_grade=True))
    assert fallback.source == "template" and "Bright Lane" in fallback.body
    assert draft_outreach(PROFILE, lead, "pitch", None).source == "template"


@respx.mock
def test_hubspot_gets_a_deal_with_the_lead_details():
    route = respx.post("https://api.hubapi.com/crm/v3/objects/deals").mock(
        return_value=httpx.Response(201, json={"id": "987"}))
    lead = make_lead("1", "Build a Django API", budget=Budget(maximum=8000, currency="USD"))
    link = HubSpot("pat-secret").push(lead, pitch="We built 3 of these.")
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer pat-secret"
    body = json.loads(sent.content)["properties"]
    assert body["dealname"] == "Build a Django API" and body["amount"] == "8000" and "We built 3" in body["description"]
    assert link.crm == "hubspot" and link.external_id == "987"


@respx.mock
def test_pipedrive_gets_a_deal_and_a_note():
    deal = respx.post("https://api.pipedrive.com/v1/deals").mock(
        return_value=httpx.Response(201, json={"success": True, "data": {"id": 45}}))
    note = respx.post("https://api.pipedrive.com/v1/notes").mock(
        return_value=httpx.Response(201, json={"success": True, "data": {"id": 1}}))
    link = Pipedrive("pd-token").push(make_lead("1", "Logo design"), pitch="Hello")
    assert deal.calls[0].request.headers["x-api-token"] == "pd-token"
    assert json.loads(note.calls[0].request.content)["deal_id"] == 45 and link.external_id == "45"


@respx.mock
def test_crm_errors_are_reported_without_the_token():
    respx.post("https://api.hubapi.com/crm/v3/objects/deals").mock(return_value=httpx.Response(401, json={}))
    with pytest.raises(CrmError) as caught:
        HubSpot("pat-secret").push(make_lead("1", "x"), pitch="")
    assert "401" in str(caught.value) and "pat-secret" not in str(caught.value)


def test_team_drafts_edits_sends_and_tracks_outreach(web, monkeypatch):
    from gigscout import outreach as outreach_module

    sent = []
    monkeypatch.setattr(outreach_module, "send_email", lambda settings, to, subject, body: sent.append((to, subject)))
    client, platform = stocked(web, smtp_host="smtp.example.com", smtp_from="scout@example.com")
    assert client.get("/api/outreach/config").json() == {"email_ready": True, "crms": []}

    draft = client.post("/api/outreach", json={"lead_id": "fake:1"})
    assert draft.status_code == 201
    d = draft.json()
    assert d["status"] == "draft" and d["channel"] == "bid" and d["body"]

    bad = client.put(f"/api/outreach/{d['id']}", json={"channel": "email", "to": "cto@client.com",
                                                     "subject": "Hi\nBcc: x@evil.com", "body": "Hello"})
    assert bad.status_code == 422  # no header injection
    edited = client.put(f"/api/outreach/{d['id']}", json={"channel": "email", "to": "cto@client.com",
                                                        "subject": "Your Django API", "body": "Hello there"})
    assert edited.status_code == 200 and edited.json()["to"] == "cto@client.com"

    result = client.post(f"/api/outreach/{d['id']}/send")
    assert result.status_code == 200 and result.json()["status"] == "sent" and result.json()["sent_at"]
    assert sent == [("cto@client.com", "Your Django API")]
    assert client.post(f"/api/outreach/{d['id']}/send").status_code == 409  # never twice
    assert client.put(f"/api/outreach/{d['id']}", json={"channel": "email", "to": "x@y.com", "subject": "s",
                                                      "body": "b"}).status_code == 409  # sent is final
    with platform.sessions() as session:
        assert session.get(LeadState, "fake:1").status == "contacted"

    replied = client.post(f"/api/outreach/{d['id']}/status", json={"status": "replied"})
    assert replied.json()["status"] == "replied"
    history = client.get("/api/outreach", params={"lead_id": "fake:1"}).json()
    assert [h["status"] for h in history] == ["replied"]
    assert client.post("/api/outreach", json={"lead_id": "nope:1"}).status_code == 404


def test_bid_copy_is_marked_sent_without_email(web, monkeypatch):
    from gigscout import outreach as outreach_module

    monkeypatch.setattr(outreach_module, "send_email", lambda *a: pytest.fail("bids are pasted, not emailed"))
    client, _ = stocked(web)
    d = client.post("/api/outreach", json={"lead_id": "fake:2"}).json()
    assert client.post(f"/api/outreach/{d['id']}/send").json()["status"] == "sent"


def test_email_needs_smtp(web):
    client, _ = stocked(web)
    d = client.post("/api/outreach", json={"lead_id": "fake:1"}).json()
    client.put(f"/api/outreach/{d['id']}", json={"channel": "email", "to": "a@b.com", "subject": "s", "body": "b"})
    response = client.post(f"/api/outreach/{d['id']}/send")
    assert response.status_code == 409 and "SMTP" in response.json()["detail"]


def test_leads_are_pushed_to_the_crm_once(web, monkeypatch):
    from gigscout import crm as crm_module

    pushed = []

    def fake_push(self, lead, pitch):
        pushed.append(lead.id)
        return crm_module.CrmLink(crm="hubspot", external_id="77", url="https://app.hubspot.com/deal/77")

    monkeypatch.setattr(crm_module.HubSpot, "push", fake_push)
    client, _ = stocked(web, hubspot_token=SecretStr("pat-x"))
    assert client.get("/api/outreach/config").json()["crms"] == ["hubspot"]
    first = client.post("/api/outreach/crm", json={"lead_id": "fake:1"})
    assert first.status_code == 200 and first.json()["links"][0]["external_id"] == "77"
    again = client.post("/api/outreach/crm", json={"lead_id": "fake:1"}).json()
    assert again["links"][0]["external_id"] == "77" and pushed == ["fake:1"]  # not duplicated
    assert client.get("/api/outreach/crm", params={"lead_id": "fake:1"}).json()["links"][0]["crm"] == "hubspot"


def test_crm_sync_without_a_crm_says_how_to_connect_one(web):
    client, _ = stocked(web)
    response = client.post("/api/outreach/crm", json={"lead_id": "fake:1"})
    assert response.status_code == 409 and "GIGSCOUT_HUBSPOT_TOKEN" in response.json()["detail"]


def test_draft_model_rejects_header_injection():
    with pytest.raises(ValueError):
        OutreachDraft(channel="email", to="a@b.com", subject="x\r\nBcc: y", body="b", source="template")


def test_outreach_times_are_marked_utc(web):
    client, _ = stocked(web)
    d = client.post("/api/outreach", json={"lead_id": "fake:2"}).json()
    assert d["created_at"].endswith(("Z", "+00:00"))


@pytest.mark.parametrize("address", ["a@x.com, b@y.com", "a@x.com;b@y.com", "Boss <a@x.com>", "not-an-email", ""])
def test_a_lead_email_that_is_not_exactly_one_address_falls_back_to_a_bid(address):
    lead = make_lead("1", "Need SEO", kind="inbound", client=Client(email=address or None))
    draft = template_draft(PROFILE, lead, pitch="")
    assert draft.channel == "bid" and draft.to is None


def test_the_hourly_email_cap_counts_who_sent_not_who_drafted(web, monkeypatch):
    from gigscout import outreach as outreach_module
    from gigscout.platform.tables import Outreach, utcnow
    from gigscout.web import routes_outreach

    monkeypatch.setattr(outreach_module, "send_email", lambda *a: None)
    monkeypatch.setattr(routes_outreach, "HOURLY_EMAIL_LIMIT", 2)
    client, platform = stocked(web, smtp_host="smtp.example.com", smtp_from="scout@example.com")
    with platform.sessions() as session:  # two emails this admin sent from drafts someone else wrote
        for _ in range(2):
            session.add(Outreach(lead_id="fake:1", channel="email", to_address="a@b.com", subject="s", body="b",
                                 status="sent", created_by="other@x.com", sent_by=ADMIN_EMAIL, sent_at=utcnow()))
        session.commit()
    d = client.post("/api/outreach", json={"lead_id": "fake:1"}).json()
    client.put(f"/api/outreach/{d['id']}", json={"channel": "email", "to": "c@d.com", "subject": "s", "body": "b"})
    assert client.post(f"/api/outreach/{d['id']}/send").status_code == 429
