"""Inbound enquiries from the company's website form, Typeform, and Meta lead ads."""

import base64
import hashlib
import hmac
import json

import httpx
import respx
from pydantic import SecretStr

from gigscout.inbound import forms
from tests.conftest import login

FORM_KEY = "k" * 32


def test_common_field_names_fill_the_client_and_budget():
    fields = forms.clean({"First Name": "Ana", "Last Name": "Diaz", "Email": "ana@bakery.com",
                          "Company": "Bakery Ltd", "Budget": "$5,000 - $8,000", "Message": "We need a new site",
                          "Timeline": "Q1"})
    lead = forms.to_lead("website_form", "abc", fields, "Website")
    assert lead.kind == "inbound" and lead.title == "Website enquiry from Bakery Ltd"
    assert lead.client.email == "ana@bakery.com" and lead.client.name == "Bakery Ltd"
    assert (lead.budget.minimum, lead.budget.maximum, lead.budget.currency) == (5000, 8000, "USD")
    assert "Contact: Ana Diaz" in lead.description and "We need a new site" in lead.description
    assert "Timeline: Q1" in lead.description


def test_answers_are_capped():
    fields = forms.clean({f"q{i}": "x" * 5000 for i in range(100)})
    assert len(fields) == forms.MAX_FIELDS and all(len(v) == forms.MAX_VALUE_CHARS for v in fields.values())


def test_website_form_is_off_until_a_key_is_set(web):
    client, _ = web()
    assert client.post(f"/webhooks/form/{FORM_KEY}", json={"email": "a@b.com"}).status_code == 404


def test_website_form_needs_its_key(web):
    client, _ = web(website_form_key=SecretStr(FORM_KEY))
    assert client.post("/webhooks/form/wrong", json={"email": "a@b.com"}).status_code == 404


def test_a_plain_html_form_gets_a_thank_you_page_and_a_lead(web):
    client, platform = web(website_form_key=SecretStr(FORM_KEY))
    response = client.post(f"/webhooks/form/{FORM_KEY}", data={"name": "Ana", "email": "ana@b.com",
                                                              "message": "Need an app"})
    assert response.status_code == 200 and "Thank you" in response.text
    leads = [r.lead for r in platform.service.deps.index.records() if r.lead.source == "website_form"]
    assert len(leads) == 1 and leads[0].client.email == "ana@b.com"
    again = client.post(f"/webhooks/form/{FORM_KEY}", json={"name": "Ana", "email": "ana@b.com",
                                                           "message": "Need an app"})
    assert again.json() == {"status": "duplicate"}  # a double submit is one lead


def test_bots_that_fill_the_honeypot_are_dropped_quietly(web):
    client, platform = web(website_form_key=SecretStr(FORM_KEY))
    response = client.post(f"/webhooks/form/{FORM_KEY}", json={"email": "bot@x.com", "website_url": "http://spam"})
    assert response.json() == {"status": "stored"}
    assert not [r for r in platform.service.deps.index.records() if r.lead.source == "website_form"]


def test_one_sender_cannot_flood_the_form(web, monkeypatch):
    from gigscout.web import routes_inbound

    monkeypatch.setattr(routes_inbound, "_form_limit", routes_inbound._SenderLimit(2))
    client, _ = web(website_form_key=SecretStr(FORM_KEY))
    codes = [client.post(f"/webhooks/form/{FORM_KEY}", json={"message": f"hi {i}"}).status_code for i in range(3)]
    assert codes == [200, 200, 429]


TYPEFORM = {"event_type": "form_response", "form_response": {
    "token": "tok123",
    "definition": {"fields": [{"id": "f1", "title": "What's your name?"}, {"id": "f2", "title": "Email"},
                              {"id": "f3", "title": "Which service?"}, {"id": "f4", "title": "Budget"}]},
    "answers": [
        {"type": "text", "text": "Ana", "field": {"id": "f1"}},
        {"type": "email", "email": "ana@b.com", "field": {"id": "f2"}},
        {"type": "choice", "choice": {"label": "Mobile app"}, "field": {"id": "f3"}},
        {"type": "text", "text": "10000", "field": {"id": "f4"}},
    ]}}


def typeform_signature(body: bytes, secret: str) -> str:
    return "sha256=" + base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_typeform_responses_are_verified_and_stored(web):
    client, platform = web(typeform_webhook_secret=SecretStr("tf-secret"))
    body = json.dumps(TYPEFORM).encode()
    bad = client.post("/webhooks/typeform", content=body, headers={"typeform-signature": "sha256=nope"})
    assert bad.status_code == 401
    ok = client.post("/webhooks/typeform", content=body,
                     headers={"typeform-signature": typeform_signature(body, "tf-secret")})
    assert ok.json() == {"status": "stored"}
    lead = platform.service.deps.index.get("typeform:tok123")
    assert lead.client.email == "ana@b.com" and "Mobile app" in lead.description and lead.budget.maximum == 10000


def meta_signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


META = {"meta_app_secret": SecretStr("app-secret"), "meta_verify_token": SecretStr("verify-me"),
        "meta_page_access_token": SecretStr("page-token")}


def test_meta_subscription_check_echoes_the_challenge(web):
    client, _ = web(**META)
    ok = client.get("/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                              "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert client.get("/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "wrong",
                                                "hub.challenge": "1"}).status_code == 403


@respx.mock
def test_meta_lead_ads_are_fetched_with_the_page_token(web):
    graph = respx.get("https://graph.facebook.com/v21.0/444555666").mock(return_value=httpx.Response(200, json={
        "field_data": [{"name": "full_name", "values": ["Ana Diaz"]}, {"name": "email", "values": ["ana@b.com"]},
                       {"name": "what_do_you_need", "values": ["SEO audit"]}]}))
    client, platform = web(**META)
    body = json.dumps({"object": "page", "entry": [{"changes": [
        {"field": "leadgen", "value": {"leadgen_id": "444555666", "page_id": "1"}}]}]}).encode()
    assert client.post("/webhooks/meta", content=body,
                       headers={"x-hub-signature-256": "sha256=bad"}).status_code == 401
    signed = {"x-hub-signature-256": meta_signature(body, "app-secret")}
    ok = client.post("/webhooks/meta", content=body, headers=signed)
    assert ok.json() == {"status": "stored"}
    request = graph.calls[0].request
    assert request.headers["authorization"] == "Bearer page-token" and "page-token" not in str(request.url)
    lead = platform.service.deps.index.get("meta_lead_ads:444555666")
    assert lead.title == "Meta lead ad enquiry from Ana Diaz" and "SEO audit" in lead.description


def test_connectors_list_every_inbound_channel(web):
    client, _ = web(typeform_webhook_secret=SecretStr("s"))
    login(client)
    pushed = {s["name"]: s["enabled"] for s in client.get("/api/admin/sources").json() if s["channel"] == "push"}
    assert pushed == {"google_ads": False, "website_form": False, "typeform": True, "meta_lead_ads": False}
