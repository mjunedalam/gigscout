"""Lead assignment and follow-ups: who owns a lead, when to chase it, and filtering by both."""

from datetime import date, timedelta

from tests.conftest import ADMIN_EMAIL, MEMBER_EMAIL, login, make_lead


def setup(web):
    client, platform = web()
    platform.index_for(1).add_new([make_lead("1", "Django API"), make_lead("2", "React app")])
    login(client)
    people = {m["name"]: m["id"] for m in client.get("/api/workspaces/current/members").json()}
    return client, platform, people


def test_leads_can_be_assigned_followed_up_and_filtered(web):
    client, platform, people = setup(web)
    events = []
    platform.bus.publish = lambda type_, data=None, workspace_id=None: events.append((type_, data))
    rep = people["Member"]
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    view = client.patch("/api/leads/fake:1", json={"assigned_to": rep, "follow_up_on": yesterday}).json()

    assert view["assigned_to"] == rep and view["assignee"] == "Member" and view["follow_up_on"] == yesterday
    assert ("lead.assigned", {"id": "fake:1", "title": "Django API", "by": "Admin", "to": "Member", "user_id": rep}) \
        in events
    login(client, MEMBER_EMAIL)
    mine = client.get("/api/leads", params={"owner": "me"}).json()["items"]
    assert [v["lead"]["id"] for v in mine] == ["fake:1"]
    assert [v["lead"]["id"] for v in client.get("/api/leads", params={"due": True}).json()["items"]] == ["fake:1"]
    unassigned = client.get("/api/leads", params={"owner": "unassigned"}).json()["items"]
    assert [v["lead"]["id"] for v in unassigned] == ["fake:2"]


def test_assignment_and_follow_up_can_be_cleared_without_touching_the_rest(web):
    client, _, people = setup(web)
    client.patch("/api/leads/fake:1", json={"assigned_to": people["Admin"], "follow_up_on": "2030-01-01",
                                            "status": "contacted", "notes": "called"})
    view = client.patch("/api/leads/fake:1", json={"assigned_to": None, "follow_up_on": None}).json()
    assert view["assigned_to"] is None and view["follow_up_on"] is None
    assert view["status"] == "contacted" and view["notes"] == "called"


def test_leads_go_only_to_people_in_the_workspace(web):
    client, _, _ = setup(web)
    assert client.patch("/api/leads/fake:1", json={"assigned_to": 999}).status_code == 422
    login(client, ADMIN_EMAIL)
    other = client.post("/api/workspaces", json={"name": "Elsewhere"}).json()["id"]
    outsider = client.post("/api/admin/users", headers={"X-Workspace": str(other)},
                           json={"email": "out@x.com", "name": "Out", "password": "correct-horse-battery"}).json()
    assert client.patch("/api/leads/fake:1", json={"assigned_to": outsider["id"]}).status_code == 422
