"""Pitches: the agents draft them after each run, people approve, edit or reject them, and silence gets a follow-up."""

from datetime import timedelta

import pytest

from gigscout.models import AgencyProfile, Budget, Client
from gigscout.outreach import follow_up_draft
from gigscout.platform.tables import AuditLog, LeadState, Outreach, utcnow
from tests.conftest import MEMBER_EMAIL, FakeReasoner, FakeSource, login, make_lead, wait_for_run

AUTOPILOT = {"auto_draft": True, "min_score": 0.0, "max_per_run": 5, "follow_up_days": 0, "require_admin": False}
PROFILE = AgencyProfile(name="Bright Lane", company_type="Marketing agency", services=("SEO",))


@pytest.fixture
def desk(web, sample_leads):
    """The app with an LLM, signed in as the owner."""
    fitting = [make_lead(str(n), title, f"{title}: a python django and react team wanted",
                         budget=Budget(maximum=9000, currency="USD")) for n, title in
               ((4, "SaaS MVP for clinics"), (5, "AI chatbot integration"), (6, "Mobile app for a fintech"))]
    client, platform = web(sources=[FakeSource("fake", [*sample_leads, *fitting])], reasoner=FakeReasoner())
    login(client)
    return client, platform


def scout(client) -> dict:
    profile_id = client.get("/api/profiles").json()[0]["id"]
    run = client.post("/api/runs", json={"profile_id": profile_id, "mode": "pipeline"}).json()
    finished = wait_for_run(client, run["id"])
    assert finished["status"] == "succeeded"
    return finished


def pending(client) -> list[dict]:
    return client.get("/api/pitches", params={"status": "pending"}).json()["items"]


def test_autopilot_is_off_until_turned_on(desk):
    client, _ = desk
    assert client.get("/api/pitches/settings").json()["auto_draft"] is False
    scout(client)
    assert pending(client) == [] and client.get("/api/pitches/summary").json()["pending"] == 0


def test_after_a_run_the_agents_draft_pitches_for_the_best_new_leads(desk):
    client, _ = desk
    assert client.put("/api/pitches/settings", json=AUTOPILOT).status_code == 200
    run = scout(client)

    items = pending(client)
    assert items and all(i["outreach"]["created_by"] == "GigScout agents" for i in items)
    assert all(i["outreach"]["run_id"] == run["id"] and i["outreach"]["source"] == "ai" for i in items)
    first = items[0]
    assert first["lead"]["title"] and first["score"] is not None and first["can_approve"]
    assert [i["score"] for i in items] == sorted((i["score"] for i in items), reverse=True)
    assert client.get("/api/pitches/summary").json()["pending"] == len(items)

    scout(client)  # the same leads again: one pitch per lead, never two
    assert len(pending(client)) == len(items)


def test_autopilot_respects_the_score_floor_and_the_cap(desk):
    client, _ = desk
    client.put("/api/pitches/settings", json={**AUTOPILOT, "max_per_run": 1})
    scout(client)
    assert len(pending(client)) == 1

    client.put("/api/pitches/settings", json={**AUTOPILOT, "min_score": 1.0})
    scout(client)
    assert len(pending(client)) == 1  # nothing scores a perfect 1.0


def test_leads_already_being_worked_get_no_pitch(desk):
    client, platform = desk
    with platform.sessions() as session:
        session.add(LeadState(workspace_id=1, lead_id="fake:1", status="proposal"))
        session.commit()
    client.put("/api/pitches/settings", json=AUTOPILOT)
    scout(client)
    assert "fake:1" not in {i["lead"]["id"] for i in pending(client)}


def test_people_approve_edit_or_reject_and_admins_can_be_required(desk):
    client, platform = desk
    client.put("/api/pitches/settings", json={**AUTOPILOT, "require_admin": True})
    scout(client)
    first, second = (i["outreach"] for i in pending(client)[:2])

    login(client, MEMBER_EMAIL)
    assert client.put(f"/api/outreach/{first['id']}", json={"channel": "bid", "to": None, "subject": "",
                                                            "body": "Edited by the rep"}).status_code == 200
    refused = client.post(f"/api/outreach/{first['id']}/send")
    assert refused.status_code == 403 and "admin" in refused.json()["detail"]
    assert client.post(f"/api/outreach/{first['id']}/reject", json={"note": "no"}).status_code == 403
    assert all(not i["can_approve"] for i in pending(client))

    login(client)
    approved = client.post(f"/api/outreach/{first['id']}/send").json()
    assert approved["status"] == "sent" and approved["body"] == "Edited by the rep" and approved["reviewed_by"]
    rejected = client.post(f"/api/outreach/{second['id']}/reject", json={"note": "  Too generic  "}).json()
    assert rejected["status"] == "rejected" and rejected["review_note"] == "Too generic"
    assert client.post(f"/api/outreach/{second['id']}/send").status_code == 409  # rejected is final

    statuses = {s: [i["outreach"]["id"] for i in client.get("/api/pitches", params={"status": s}).json()["items"]]
                for s in ("sent", "rejected")}
    assert statuses == {"sent": [first["id"]], "rejected": [second["id"]]}
    with platform.sessions() as session:
        actions = {a.action for a in session.query(AuditLog)}
        state = session.get(LeadState, (1, rejected["lead_id"]))
    assert {"pitch.auto_draft", "outreach.send", "outreach.reject"} <= actions
    assert state is None or state.status == "new"  # rejecting a pitch does not touch the lead


def test_only_admins_change_the_autopilot(desk):
    client, _ = desk
    login(client, MEMBER_EMAIL)
    assert client.get("/api/pitches/settings").status_code == 200
    assert client.put("/api/pitches/settings", json=AUTOPILOT).status_code == 403
    login(client)
    assert client.put("/api/pitches/settings", json={**AUTOPILOT, "min_score": 2}).status_code == 422


def test_silence_gets_one_follow_up_draft(desk, sample_leads):
    client, platform = desk
    platform.index_for(1).add_new(sample_leads)
    client.put("/api/pitches/settings", json={**AUTOPILOT, "auto_draft": False, "follow_up_days": 3})
    old = utcnow() - timedelta(days=4)
    with platform.sessions() as session:
        for lead_id, status, sent_at in (("fake:1", "sent", old), ("fake:3", "replied", old),
                                         ("fake:2", "sent", utcnow())):
            session.add(Outreach(workspace_id=1, lead_id=lead_id, channel="email", to_address="cto@client.com",
                                 subject="Your Django API", body="Hello", status=status, created_by="a@b.com",
                                 sent_at=sent_at, sent_by="a@b.com"))
        session.commit()

    assert platform.pitches.follow_ups(1) == 1
    [follow_up] = pending(client)
    assert follow_up["lead"]["id"] == "fake:1" and follow_up["outreach"]["kind"] == "follow_up"
    assert follow_up["outreach"]["subject"] == "Re: Your Django API" and follow_up["outreach"]["to"] == "cto@client.com"
    assert platform.pitches.follow_ups(1) == 0  # one follow-up per message


def test_follow_up_text_quotes_the_first_message():
    lead = make_lead("1", "SEO for a bakery", client=Client(name="Ana"))
    draft = follow_up_draft(PROFILE, lead, "ana@bakery.com", "Re: SEO for a bakery", "We grew traffic 2x.")
    assert draft.channel == "email" and draft.to == "ana@bakery.com"
    assert draft.subject == "Re: SEO for a bakery"  # never "Re: Re:"
    assert "Hi Ana," in draft.body and "> We grew traffic 2x." in draft.body and "Bright Lane" in draft.body
