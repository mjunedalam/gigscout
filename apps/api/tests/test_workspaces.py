"""Workspaces: each company's leads, profiles, runs, sources and members stay its own."""

import sqlite3

from sqlalchemy import select

from gigscout.platform.db import create_db
from gigscout.platform.tables import Connector, LeadState, Membership, Workspace
from tests.conftest import MEMBER_EMAIL, PASSWORD, login, make_lead, wait_for_run

OTHER_EMAIL = "boss@bright-studio.com"


def second_workspace(client):
    """The platform admin creates 'Bright Studio' and adds its own owner, who belongs nowhere else."""
    login(client)
    created = client.post("/api/workspaces", json={"name": "Bright Studio"})
    assert created.status_code == 201
    ws = created.json()["id"]
    added = client.post("/api/admin/users", headers={"X-Workspace": str(ws)},
                        json={"email": OTHER_EMAIL, "name": "Boss", "role": "owner", "password": PASSWORD})
    assert added.status_code == 201, added.text
    return ws


def test_a_new_workspace_starts_empty_and_sees_nothing_of_the_first(web):
    client, platform = web()
    platform.index_for(1).add_new([make_lead("1", "Django API for a clinic")])
    ws = second_workspace(client)
    login(client, OTHER_EMAIL)

    me = client.get("/api/auth/me").json()
    assert [w["name"] for w in me["workspaces"]] == ["Bright Studio"]
    assert client.get("/api/leads").json()["total"] == 0  # its first workspace is used without a header
    assert client.get("/api/profiles").json() == []
    assert client.get("/api/runs").json() == []
    assert client.get("/api/leads/fake:1").status_code == 404
    for path in ("/api/leads", "/api/profiles", "/api/runs"):
        assert client.get(path, headers={"X-Workspace": "1"}).status_code == 404  # not a member there
    assert client.get("/api/workspaces/current").json()["id"] == ws


def test_runs_store_leads_in_their_own_workspace(web):
    client, platform = web()
    ws = second_workspace(client)
    login(client, OTHER_EMAIL)
    profile = client.post("/api/profiles", json={"name": "Bright", "pitch": "Django APIs in Python",
                                                 "skills": ["python", "django"]})
    assert profile.status_code == 201, profile.text
    run = client.post("/api/runs", json={"profile_id": profile.json()["id"], "mode": "pipeline"}).json()

    assert wait_for_run(client, run["id"])["status"] == "succeeded"
    assert platform.index_for(ws).count() == 3 and platform.index_for(1).count() == 0
    assert client.get("/api/leads").json()["total"] == 3
    with platform.sessions() as session:
        assert {s.workspace_id for s in session.scalars(select(LeadState))} == {ws}

    login(client, MEMBER_EMAIL)  # a member of the first workspace sees neither the run nor its leads
    assert client.get("/api/runs").json() == [] and client.get("/api/leads").json()["total"] == 0
    assert client.get(f"/api/runs/{run['id']}").status_code == 404
    assert client.post("/api/runs", json={"profile_id": profile.json()["id"], "mode": "pipeline"}).status_code == 404


def test_only_platform_admins_create_workspaces_and_only_owners_make_owners(web):
    client, _ = web()
    login(client, MEMBER_EMAIL)
    assert client.post("/api/workspaces", json={"name": "Mine"}).status_code == 403
    assert client.get("/api/admin/users").status_code == 403  # members do not manage the workspace

    login(client)
    me = client.get("/api/admin/users").json()
    rep = next(u for u in me if u["email"] == MEMBER_EMAIL)
    assert client.patch(f"/api/admin/users/{rep['id']}", json={"role": "admin"}).json()["role"] == "admin"
    login(client, MEMBER_EMAIL)
    assert client.patch(f"/api/admin/users/{rep['id']}", json={"role": "owner"}).status_code == 403


def test_a_workspace_admin_cannot_take_over_accounts_that_belong_elsewhere(web):
    client, _ = web()
    ws = second_workspace(client)
    login(client, OTHER_EMAIL)
    added = client.post("/api/admin/users", json={"email": MEMBER_EMAIL, "name": "Rep", "role": "member"})
    assert added.status_code == 201  # an existing account joins without a password
    rep = added.json()["id"]
    assert client.patch(f"/api/admin/users/{rep}", json={"password": "a-brand-new-password"}).status_code == 403
    assert client.patch(f"/api/admin/users/{rep}", json={"is_active": False}).status_code == 403
    assert client.delete(f"/api/admin/users/{rep}").status_code == 204  # removing them from here is fine
    login(client, MEMBER_EMAIL)  # their password still works
    assert ws not in [w["id"] for w in client.get("/api/auth/me").json()["workspaces"]]


def test_each_workspace_has_its_own_website_form_address(web):
    client, platform = web()
    ws = second_workspace(client)
    login(client, OTHER_EMAIL)
    path = client.get("/api/workspaces/current").json()["form_path"]
    assert path.startswith("/webhooks/form/")

    assert client.post(path, json={"email": "ana@b.com", "message": "Need an app"}).json() == {"status": "stored"}
    assert platform.index_for(ws).count() == 1 and platform.index_for(1).count() == 0
    assert client.post("/webhooks/form/not-a-real-key-at-all", json={"message": "x"}).status_code == 404

    rotated = client.post("/api/workspaces/current/form-key").json()["form_path"]
    assert rotated != path and client.post(path, json={"message": "old address"}).status_code == 404


def test_live_events_stay_in_their_workspace(web):
    client, platform = web()
    ws = second_workspace(client)
    platform.bus.publish("lead.inbound", {"title": "first"}, 1)
    platform.bus.publish("lead.inbound", {"title": "second"}, ws)
    login(client, OTHER_EMAIL)
    assert [e["data"]["title"] for e in client.get("/api/events/recent").json()] == ["second"]


def test_audit_log_is_per_workspace(web):
    client, _ = web()
    ws = second_workspace(client)
    login(client, OTHER_EMAIL)
    client.patch("/api/workspaces/current", json={"name": "Bright Studio Ltd"})
    actions = {a["action"] for a in client.get("/api/admin/audit").json()}
    assert "workspace.rename" in actions and "member.update" not in actions
    login(client)
    first = {a["action"] for a in client.get("/api/admin/audit", headers={"X-Workspace": "1"}).json()}
    assert "workspace.rename" not in first
    assert client.get("/api/workspaces/current", headers={"X-Workspace": str(ws)}).json()["name"] == "Bright Studio Ltd"


def test_an_existing_database_moves_into_the_first_workspace(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(254) UNIQUE, name VARCHAR(120), role VARCHAR(16),
            password_hash VARCHAR(300), is_active BOOLEAN, created_at DATETIME, last_login_at DATETIME);
        INSERT INTO users VALUES (1, 'a@x.com', 'A', 'admin', 'h', 1, '2026-01-01 00:00:00', NULL);
        INSERT INTO users VALUES (2, 'b@x.com', 'B', 'member', 'h', 1, '2026-01-01 00:00:00', NULL);
        CREATE TABLE agency_profiles (id INTEGER PRIMARY KEY, name VARCHAR(120), data JSON, created_at DATETIME,
            updated_at DATETIME);
        INSERT INTO agency_profiles VALUES (1, 'Acme Software Studio', '{}', '2026-01-01', '2026-01-01');
        CREATE TABLE lead_states (lead_id VARCHAR(300) PRIMARY KEY, status VARCHAR(16), notes TEXT, score FLOAT,
            reasons TEXT, red_flags TEXT, pitch TEXT, last_run_id VARCHAR(36), updated_by VARCHAR(254),
            updated_at DATETIME);
        CREATE INDEX ix_lead_states_status ON lead_states (status);
        INSERT INTO lead_states VALUES ('fake:1', 'won', 'great client', 0.9, 'fit', '', 'pitch', NULL, NULL,
            '2026-01-02 00:00:00');
        CREATE TABLE connectors (id INTEGER PRIMARY KEY, name VARCHAR(60) UNIQUE, label VARCHAR(120), url VARCHAR(500),
            kind VARCHAR(8), feed_url VARCHAR(500), enabled BOOLEAN, status VARCHAR(16), last_error TEXT,
            checked_at DATETIME, created_by VARCHAR(254), created_at DATETIME);
        INSERT INTO connectors VALUES (1, 'jobs', 'Jobs', 'https://jobs.example', 'feed', NULL, 1, 'ok', NULL, NULL,
            'a@x.com', '2026-01-01');
    """)
    db.commit()
    db.close()

    _, sessions = create_db(f"sqlite:///{path}")
    create_db(f"sqlite:///{path}")  # running again changes nothing

    with sessions() as session:
        [workspace] = session.scalars(select(Workspace)).all()
        assert workspace.id == 1 and workspace.name == "Acme Software Studio" and len(workspace.form_key) >= 24
        roles = {m.user_id: m.role for m in session.scalars(select(Membership))}
        assert roles == {1: "owner", 2: "member"}
        state = session.get(LeadState, (1, "fake:1"))
        assert state.status == "won" and state.notes == "great client" and state.learned == 0
        assert session.scalar(select(Connector)).workspace_id == 1


def test_an_admin_cannot_change_or_remove_an_owner(web):
    client, _ = web()
    ws = second_workspace(client)
    login(client, OTHER_EMAIL)  # the owner adds an admin, who then turns on them
    admin = client.post("/api/admin/users", json={"email": "ops@bright-studio.com", "name": "Ops", "role": "admin",
                                                  "password": PASSWORD}).json()
    owner = next(u for u in client.get("/api/admin/users").json() if u["email"] == OTHER_EMAIL)
    login(client, admin["email"])
    assert client.get("/api/workspaces/current").json()["id"] == ws
    for change in ({"password": "taken-over-password"}, {"is_active": False}, {"role": "member"}):
        assert client.patch(f"/api/admin/users/{owner['id']}", json=change).status_code == 403
    assert client.delete(f"/api/admin/users/{owner['id']}").status_code == 403
    login(client, OTHER_EMAIL)  # the owner's password still works


def test_adding_an_existing_account_never_gives_control_of_it(web):
    client, platform = web()
    second_workspace(client)
    login(client)  # a lone account created by the first workspace, then removed from it
    lone = client.post("/api/admin/users", json={"email": "lone@x.com", "name": "Lone", "role": "member",
                                                 "password": PASSWORD}).json()
    assert client.delete(f"/api/admin/users/{lone['id']}").status_code == 204
    login(client, OTHER_EMAIL)  # another workspace adds it: it belongs nowhere else, but was not created here
    assert client.post("/api/admin/users", json={"email": "lone@x.com", "name": "Lone", "role": "member"}
                       ).status_code == 201
    assert client.patch(f"/api/admin/users/{lone['id']}", json={"password": "taken-over-password"}).status_code == 403
    login(client, "lone@x.com")


def test_the_suite_runs_on_postgres_when_asked(web):
    """Guards the Postgres CI job: with GIGSCOUT_TEST_POSTGRES_URL set, tests must not quietly fall back to SQLite."""
    import os

    _, platform = web()
    expected = "postgresql" if os.environ.get("GIGSCOUT_TEST_POSTGRES_URL") else "sqlite"
    assert platform.engine.dialect.name == expected


def test_the_setup_checklist_follows_what_the_workspace_has_done(web):
    client, _ = web()
    second_workspace(client)
    login(client, OTHER_EMAIL)

    def done():
        return {s["id"] for s in client.get("/api/workspaces/current/setup").json() if s["done"]}

    assert done() == {"team"}  # the platform admin who created it and its owner
    client.post("/api/profiles", json={"name": "Bright", "pitch": "Apps", "skills": ["react"]})
    client.put("/api/admin/sources/fake/enabled", json={"enabled": False})
    assert done() == {"profile", "sources", "team"}


def test_viewers_see_everything_and_change_nothing(web):
    client, platform = web()
    platform.index_for(1).add_new([make_lead("1", "Django API")])
    login(client)
    viewer = client.post("/api/admin/users", json={"email": "look@acme.com", "name": "Looker", "role": "viewer",
                                                   "password": PASSWORD}).json()
    assert viewer["role"] == "viewer"
    profile = client.get("/api/profiles").json()
    login(client, "look@acme.com")
    assert client.get("/api/leads").json()["total"] == 1 and client.get("/api/runs").status_code == 200
    assert client.patch("/api/leads/fake:1", json={"status": "won"}).status_code == 403
    if profile:
        assert client.post("/api/runs", json={"profile_id": profile[0]["id"], "mode": "pipeline"}).status_code == 403
    assert client.post("/api/outreach", json={"lead_id": "fake:1"}).status_code == 403
    assert client.get("/api/admin/users").status_code == 403
