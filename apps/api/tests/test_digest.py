"""The daily digest: the best new leads, with a pitch each, by email and Slack."""

from datetime import timedelta

import httpx
import pytest
import respx

from gigscout.digest import (
    DigestSettingsView,
    UnsafeWebhook,
    build_digest,
    check_slack_webhook,
    render_markdown,
    send_slack,
)
from gigscout.models import Budget
from gigscout.platform.tables import DigestSettings, LeadState, utcnow
from tests.conftest import login, make_lead

HOOK = "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXX"


@pytest.fixture
def stored(index):
    index.add_new([
        make_lead("1", "Build a Django REST API", budget=Budget(maximum=8000, currency="USD")),
        make_lead("2", "Logo for a bakery"),
        make_lead("3", "Old but great lead"),
        make_lead("4", "Already contacted lead"),
    ])
    return index


def states(now):
    return [
        LeadState(lead_id="fake:1", score=0.82, pitch="We shipped 3 of these.", reasons="Exact stack", updated_at=now),
        LeadState(lead_id="fake:2", score=0.31, pitch="", updated_at=now),  # below the bar
        LeadState(lead_id="fake:3", score=0.9, pitch="x", updated_at=now - timedelta(days=3)),  # older than last digest
        LeadState(lead_id="fake:4", status="contacted", score=0.95, updated_at=now),  # already being worked
    ]


def test_digest_has_the_best_new_uncontacted_leads_since_last_time(stored):
    now = utcnow()
    config = DigestSettingsView(min_score=0.6, max_leads=10, last_sent_at=now - timedelta(days=1))

    digest = build_digest(states(now), stored, config, now)

    assert [lead.title for lead in digest.leads] == ["Build a Django REST API"]
    md = render_markdown(digest)
    assert "Build a Django REST API" in md and "We shipped 3 of these." in md and "$8,000" in md and "0.82" in md


def test_an_empty_digest_says_so(stored):
    digest = build_digest([], stored, DigestSettingsView(), utcnow())
    assert digest.leads == [] and "No new qualified leads" in render_markdown(digest)


@pytest.mark.parametrize("url", ["http://hooks.slack.com/services/x", "https://evil.example/services/x",
                                 "https://hooks.slack.com.evil.example/services/x", "https://hooks.slack.com/"])
def test_only_real_slack_webhooks_are_accepted(url):
    with pytest.raises(UnsafeWebhook):
        check_slack_webhook(url)


@respx.mock
def test_slack_gets_a_message(stored):
    route = respx.post(HOOK).mock(return_value=httpx.Response(200, text="ok"))
    now = utcnow()
    send_slack(HOOK, build_digest(states(now), stored, DigestSettingsView(last_sent_at=now - timedelta(days=1)), now))
    assert route.called and "Build a Django REST API" in route.calls[0].request.content.decode()


def test_admin_configures_previews_and_sends_the_digest(web, monkeypatch):
    from gigscout import digest as digest_module

    sent = {}
    monkeypatch.setattr(digest_module, "send_slack", lambda url, d: sent.setdefault("slack", (url, len(d.leads))))
    monkeypatch.setattr(digest_module, "send_email",
                        lambda settings, to, d: sent.setdefault("email", (tuple(to), len(d.leads))))
    client, platform = web(smtp_host="smtp.example.com", smtp_from="scout@example.com")
    platform.service.deps.index.add_new([make_lead("1", "Build a Django REST API")])
    with platform.sessions() as session:
        session.add(LeadState(lead_id="fake:1", score=0.8, pitch="Hello"))
        session.commit()
    login(client)

    saved = client.put("/api/admin/digest", json={"enabled": True, "hour": 9, "emails": ["sales@acme.com"],
                                                  "slack_webhook": HOOK, "min_score": 0.6, "max_leads": 5})
    assert saved.status_code == 200
    config = client.get("/api/admin/digest").json()
    assert config["slack_configured"] and HOOK not in str(config) and config["email_ready"] is True
    assert platform.schedules.has_job("digest")

    preview = client.post("/api/admin/digest/preview").json()
    assert preview["count"] == 1 and "Build a Django REST API" in preview["markdown"]

    result = client.post("/api/admin/digest/send").json()
    assert sorted(result["sent"]) == ["email", "slack"] and result["count"] == 1
    assert sent == {"slack": (HOOK, 1), "email": (("sales@acme.com",), 1)}
    assert client.get("/api/admin/digest").json()["last_sent_at"]
    assert client.put("/api/admin/digest", json={"enabled": True, "hour": 9, "emails": [], "slack_webhook": "https://evil.example/x",
                                                  "min_score": 0.6, "max_leads": 5}).status_code == 422

    client.put("/api/admin/digest", json={"enabled": False, "hour": 9, "emails": [], "slack_webhook": None,
                                          "min_score": 0.6, "max_leads": 5})
    assert not platform.schedules.has_job("digest")
    with platform.sessions() as session:
        assert session.get(DigestSettings, 1).slack_webhook == HOOK  # None means keep the saved webhook


def test_slack_text_cannot_ping_channels_or_hide_links_from_lead_content():
    from datetime import UTC, datetime

    from gigscout.digest import Digest, DigestLead, render_slack

    nasty = DigestLead(
        id="x", title="<!channel> Win $$$ <https://evil.example|click>", url="javascript:alert(1)", kind="project",
        source="site", budget="—", score=0.9, pitch="<@U123> call me & <!here>", reasons="a > b",
    )
    text = render_slack(Digest(leads=[nasty], since=datetime.now(UTC), generated_at=datetime.now(UTC)))

    assert "<!channel>" not in text and "<!here>" not in text and "<@U123>" not in text
    assert "&lt;!channel&gt;" in text and "&amp;" in text and "a &gt; b" in text
    assert "javascript:" not in text  # links are only built for http(s) URLs
    safe = DigestLead(id="y", title="Real lead", url="https://jobs.example.com/1?a=1&b=2", kind="project",
                      source="s", budget="—", score=0.8, pitch="", reasons="")
    assert "<https://jobs.example.com/1?a=1&amp;b=2|Real lead>" in render_slack(
        Digest(leads=[safe], since=datetime.now(UTC), generated_at=datetime.now(UTC)))
