"""Upwork through its official API: admin signs in with OAuth, tokens are sealed, runs search jobs."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from pydantic import SecretStr

from gigscout import upwork
from gigscout.platform.tables import IntegrationToken
from tests.conftest import login

KEYS = {"upwork_client_id": "client-id", "upwork_client_secret": SecretStr("client-secret")}
NODE = {
    "id": "1234", "title": "Build a Django REST API", "description": "<p>Need an <b>API</b></p>",
    "ciphertext": "~01abc", "createdDateTime": "2026-11-03T10:00:00Z", "totalApplicants": 7,
    "amount": {"rawValue": "2500", "currency": "USD"}, "hourlyBudgetMin": None, "hourlyBudgetMax": None,
    "skills": [{"name": "Django"}, {"name": "Python"}], "client": {"location": {"country": "Germany"}},
}


def token_response(access="access-1", refresh="refresh-1", expires_in=86400):
    return httpx.Response(200, json={"access_token": access, "refresh_token": refresh, "token_type": "Bearer",
                                     "expires_in": expires_in})


def test_a_job_posting_becomes_a_project_lead():
    lead = upwork.parse(NODE)
    assert lead.id == "upwork:1234" and lead.url == "https://www.upwork.com/jobs/~01abc"
    assert lead.description == "Need an API" and lead.skills == ("Django", "Python") and lead.bid_count == 7
    assert lead.budget.maximum == 2500 and lead.budget.kind == "fixed" and lead.client.country == "Germany"
    hourly = upwork.parse({**NODE, "amount": None, "hourlyBudgetMin": {"rawValue": "30"},
                           "hourlyBudgetMax": {"rawValue": "60", "currency": "USD"}})
    assert hourly.budget.kind == "hourly" and (hourly.budget.minimum, hourly.budget.maximum) == (30, 60)
    assert upwork.parse({"title": "no id"}) is None


@respx.mock
def test_search_sends_the_query_and_bearer_token():
    route = respx.post(upwork.GRAPHQL_URL).mock(return_value=httpx.Response(200, json={
        "data": {"marketplaceJobPostingsSearch": {"edges": [{"node": NODE}]}}}))
    leads = upwork.UpworkSource(lambda: "tok").fetch(["django api"], limit=10)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer tok"
    assert json.loads(sent.content)["variables"]["filter"]["searchExpression_eq"] == "django api"
    assert [lead.id for lead in leads] == ["upwork:1234"]


@respx.mock
def test_upwork_errors_are_reported_without_secrets():
    respx.post(upwork.GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"errors": [{"message": "Bad scope"}]}))
    with pytest.raises(upwork.UpworkError, match="Bad scope"):
        upwork.UpworkSource(lambda: "tok").fetch(["x"], limit=5)
    respx.post(upwork.TOKEN_URL).mock(return_value=httpx.Response(401, json={}))
    with pytest.raises(upwork.UpworkError) as caught:
        upwork.refresh("client-id", "client-secret", "refresh-token")
    assert "401" in str(caught.value) and "client-secret" not in str(caught.value)


def test_tokens_cannot_be_read_with_another_secret():
    sealed = upwork.TokenVault("secret-a").seal("access")
    assert upwork.TokenVault("secret-a").open(sealed) == "access" and "access" not in sealed
    with pytest.raises(upwork.UpworkError):
        upwork.TokenVault("secret-b").open(sealed)


def test_connecting_needs_keys(web):
    client, _ = web()
    login(client)
    assert client.get("/api/admin/upwork").json()["configured"] is False
    response = client.post("/api/admin/upwork/connect")
    assert response.status_code == 409 and "GIGSCOUT_UPWORK_CLIENT_ID" in response.json()["detail"]


@respx.mock
def test_admin_connects_upwork_and_runs_can_search_it(web):
    token = respx.post(upwork.TOKEN_URL).mock(return_value=token_response())
    client, platform = web(**KEYS)
    login(client)

    url = client.post("/api/admin/upwork/connect").json()["url"]
    params = parse_qs(urlsplit(url).query)
    assert url.startswith(upwork.AUTHORIZE_URL) and params["client_id"] == ["client-id"]
    state = params["state"][0]

    client.cookies.clear()  # the cross-site redirect back from Upwork carries no session cookie
    back = client.get("/api/admin/upwork/callback", params={"code": "the-code", "state": state},
                      follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"] == "/admin/sources?upwork=connected"
    form = parse_qs(token.calls[0].request.content.decode())
    assert form["grant_type"] == ["authorization_code"] and form["code"] == ["the-code"]

    replay = client.get("/api/admin/upwork/callback", params={"code": "x", "state": state}, follow_redirects=False)
    assert "upwork=error" in replay.headers["location"]  # a state works once

    with platform.sessions() as session:
        row = session.get(IntegrationToken, "upwork")
        assert row.connected_by == "admin@acme-studio.com" and "access-1" not in row.access_token
    assert platform.upwork.access_token() == "access-1"
    assert "upwork" in platform.runs.sources_for_run()

    login(client)
    assert client.get("/api/admin/upwork").json()["connected"] is True
    assert client.delete("/api/admin/upwork").status_code == 204
    assert "upwork" not in platform.runs.sources_for_run()


@respx.mock
def test_an_expiring_token_is_refreshed(web):
    client, platform = web(**KEYS)
    platform.upwork._save(upwork.Tokens("old", "refresh-1", datetime.now(UTC) + timedelta(minutes=1)), "admin@x.com")
    refresh = respx.post(upwork.TOKEN_URL).mock(return_value=token_response(access="new", refresh="refresh-2"))
    assert platform.upwork.access_token() == "new"
    assert parse_qs(refresh.calls[0].request.content.decode())["grant_type"] == ["refresh_token"]
    assert platform.upwork.access_token() == "new" and refresh.call_count == 1  # fresh now: no second refresh


def test_a_callback_without_a_started_sign_in_is_refused(web):
    client, platform = web(**KEYS)
    back = client.get("/api/admin/upwork/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert back.status_code == 303 and "upwork=error" in back.headers["location"]
    assert platform.upwork.status()["connected"] is False
