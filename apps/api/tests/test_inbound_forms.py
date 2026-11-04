"""Inbound enquiries from the company's website form, Typeform, and Meta lead ads."""

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qsl

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
    assert pushed == {"google_ads": False, "website_form": True, "typeform": True, "meta_lead_ads": False}


def test_a_body_over_the_cap_is_refused_even_without_a_length_header(web):
    from gigscout.web import routes_inbound

    client, _ = web(website_form_key=SecretStr(FORM_KEY))

    def chunks():
        for _ in range(100):
            yield b"x" * 1024  # streamed: no Content-Length

    response = client.post(f"/webhooks/form/{FORM_KEY}", content=chunks(), headers={"content-type": "application/json"})
    assert response.status_code == 413 and routes_inbound.MAX_BODY_BYTES < 100 * 1024


def test_multipart_forms_are_refused(web):
    client, _ = web(website_form_key=SecretStr(FORM_KEY))
    response = client.post(f"/webhooks/form/{FORM_KEY}", files={"f": ("a.txt", b"x")}, data={"email": "a@b.com"})
    assert response.status_code == 415


def test_a_burst_never_locks_out_everyone_and_old_senders_are_forgotten(monkeypatch):
    from gigscout.web import routes_inbound

    clock = [0.0]
    monkeypatch.setattr(routes_inbound.time, "monotonic", lambda: clock[0])
    limit = routes_inbound._SenderLimit(per_hour=5, burst=3, burst_prefix=1)
    assert [limit.allow(f"10.0.0.{i}", "10.0.0.0/24") for i in range(3)] == [(True, False)] * 3
    assert limit.allow("10.0.0.9", "10.0.0.0/24") == (False, True)  # in a burst, that block is used up
    assert limit.allow("192.0.2.1", "192.0.2.0/24") == (True, True)  # a genuine enquiry elsewhere still lands
    clock[0] = 4000.0
    assert limit.allow("10.0.0.9", "10.0.0.0/24") == (True, False)
    assert set(limit._seen) == {"10.0.0.9", "block:10.0.0.0/24"}  # the hour passed: old senders gone


def test_spam_and_empty_forms_do_not_use_up_the_limit(web, monkeypatch):
    from gigscout.web import routes_inbound

    monkeypatch.setattr(routes_inbound, "_form_limit", routes_inbound._SenderLimit(1))
    client, _ = web(website_form_key=SecretStr(FORM_KEY))
    for _ in range(3):
        client.post(f"/webhooks/form/{FORM_KEY}", json={"website_url": "http://spam", "email": "bot@x.com"})
        client.post(f"/webhooks/form/{FORM_KEY}", json={})
    assert client.post(f"/webhooks/form/{FORM_KEY}", json={"message": "real"}).json() == {"status": "stored"}


def test_enquiries_during_a_burst_are_stored_but_flagged(web, monkeypatch):
    from gigscout.web import routes_inbound

    monkeypatch.setattr(routes_inbound, "_form_limit", routes_inbound._SenderLimit(10, burst=0, burst_prefix=5))
    client, platform = web(website_form_key=SecretStr(FORM_KEY))
    assert client.post(f"/webhooks/form/{FORM_KEY}", json={"message": "hello"}).json() == {"status": "stored"}
    lead = next(r.lead for r in platform.service.deps.index.records() if r.lead.source == "website_form")
    assert lead.description.startswith(routes_inbound.BURST_NOTE)


def test_ipv6_senders_are_grouped_by_their_64_block():
    from types import SimpleNamespace

    from gigscout.web.routes_inbound import sender_of

    def request(host):
        return SimpleNamespace(client=SimpleNamespace(host=host))

    assert sender_of(request("2001:db8:1:2::aaaa"))[0] == sender_of(request("2001:db8:1:2:ffff::1"))[0]
    assert sender_of(request("2001:db8:1:2::aaaa")) == ("2001:db8:1:2::/64", "2001:db8:1::/48")
    assert sender_of(request("203.0.113.5")) == ("203.0.113.5", "203.0.113.0/24")


def test_memory_and_volume_stay_bounded_even_under_attack():
    from gigscout.web import routes_inbound

    full = routes_inbound._SenderLimit(per_hour=5, burst=99, burst_prefix=5, ceiling=99, max_keys=6)
    results = [full.allow(f"10.0.{i}.1", f"10.0.{i}.0/24") for i in range(10)]
    assert all(ok for ok, _ in results) and len(full._seen) == 6  # memory capped, newcomers not refused...
    assert [flagged for _, flagged in results] == [False] * 3 + [True] * 7  # ...but flagged for a human to check
    flood = routes_inbound._SenderLimit(per_hour=99, burst=99, burst_prefix=99, ceiling=4, max_keys=1000)
    assert [flood.allow(f"s{i}", f"b{i}")[0] for i in range(6)] == [True] * 4 + [False] * 2  # absolute ceiling


def test_refused_requests_leave_nothing_behind():
    from gigscout.web import routes_inbound

    limit = routes_inbound._SenderLimit(per_hour=1, burst=99, burst_prefix=99, ceiling=99, max_keys=99)
    assert limit.allow("a", "blk")[0] and not limit.allow("a", "blk")[0]
    assert len(limit._all) == 1 and len(limit._seen["a"]) == 1


TURNSTILE = {"website_form_key": SecretStr(FORM_KEY), "turnstile_secret_key": SecretStr("ts-secret"),
             "turnstile_site_key": "0x4AAAAAAAsitekey"}


def siteverify(**result):
    from gigscout.inbound import turnstile

    return respx.post(turnstile.VERIFY_URL).mock(return_value=httpx.Response(200, json=result))


def website_leads(platform):
    return [r.lead for r in platform.service.deps.index.records() if r.lead.source == "website_form"]


@respx.mock
def test_with_turnstile_on_a_passed_check_stores_the_lead_without_the_token(web):
    route = siteverify(success=True)
    client, platform = web(**TURNSTILE)
    response = client.post(f"/webhooks/form/{FORM_KEY}",
                           data={"email": "ana@b.com", "message": "Need an app", "cf-turnstile-response": "tok-1"})
    assert response.status_code == 200 and "Thank you" in response.text
    sent = dict(parse_qsl(route.calls[0].request.content.decode()))
    assert sent["secret"] == "ts-secret" and sent["response"] == "tok-1"
    [lead] = website_leads(platform)
    assert "tok-1" not in lead.description and "turnstile" not in lead.description


@respx.mock
def test_with_turnstile_on_a_missing_or_failed_token_stores_nothing(web):
    route = siteverify(success=False, **{"error-codes": ["invalid-input-response"]})
    client, platform = web(**TURNSTILE)
    missing = client.post(f"/webhooks/form/{FORM_KEY}", json={"email": "bot@x.com", "message": "spam"})
    assert missing.status_code == 403 and route.call_count == 0  # no token: Cloudflare is not even asked
    page = client.post(f"/webhooks/form/{FORM_KEY}", data={"message": "spam", "cf-turnstile-response": "forged"})
    assert page.status_code == 403 and "Please try again" in page.text
    assert not website_leads(platform)


@respx.mock
def test_passed_checks_skip_the_burst_allowance_and_are_not_flagged(web, monkeypatch):
    from gigscout.web import routes_inbound

    monkeypatch.setattr(routes_inbound, "_form_limit", routes_inbound._SenderLimit(10, burst=0, burst_prefix=0))
    siteverify(success=True)
    client, platform = web(**TURNSTILE)
    for i in range(3):
        body = {"message": f"real enquiry {i}", "cf-turnstile-response": f"tok-{i}"}
        assert client.post(f"/webhooks/form/{FORM_KEY}", json=body).json() == {"status": "stored"}
    assert all(not lead.description.startswith(routes_inbound.BURST_NOTE) for lead in website_leads(platform))


@respx.mock
def test_if_cloudflare_is_down_enquiries_fall_back_to_the_ip_limits(web):
    from gigscout.inbound import turnstile

    respx.post(turnstile.VERIFY_URL).mock(side_effect=httpx.ConnectError("down"))
    client, platform = web(**TURNSTILE)
    body = {"message": "hello", "cf-turnstile-response": "tok"}
    assert client.post(f"/webhooks/form/{FORM_KEY}", json=body).json() == {"status": "stored"}
    assert len(website_leads(platform)) == 1


@respx.mock
def test_a_wrong_secret_key_does_not_throw_away_enquiries(web):
    siteverify(success=False, **{"error-codes": ["invalid-input-secret"]})
    client, _ = web(**TURNSTILE)
    body = {"message": "hello", "cf-turnstile-response": "tok"}
    assert client.post(f"/webhooks/form/{FORM_KEY}", json=body).json() == {"status": "stored"}


def test_connectors_show_the_bot_check_and_public_site_key_but_never_the_secret(web):
    client, _ = web(**TURNSTILE)
    login(client)
    response = client.get("/api/admin/sources")
    form = next(s for s in response.json() if s["name"] == "website_form")
    assert form["bot_check"] is True and form["site_key"] == "0x4AAAAAAAsitekey"
    assert "ts-secret" not in response.text
    assert "ts-secret" not in client.get("/api/admin/settings").text
