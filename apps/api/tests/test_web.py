"""The web API end to end on fakes: auth, leads, runs, schedules, dashboards, admin and the webhook."""

from pydantic import SecretStr

from tests.conftest import MEMBER_EMAIL, PASSWORD, FakeReasoner, login, wait_for_run
from tests.test_inbound import KEY, form_payload


def test_health_is_public_but_everything_else_needs_a_session(web):
    client, _ = web()
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/leads").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_login_sets_httponly_cookie_and_logout_clears_it(web):
    client, _ = web()

    response = login(client)

    assert "token" not in response.json()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    me = client.get("/api/auth/me").json()
    assert me["role"] == "admin"
    assert me["created_at"].endswith(("Z", "+00:00"))  # SQLite-naive times go out as UTC
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_is_rejected_then_rate_limited(web):
    client, _ = web()
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": MEMBER_EMAIL, "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": MEMBER_EMAIL, "password": PASSWORD}).status_code == 429


def test_account_is_rate_limited_across_client_addresses(web):
    from gigscout.platform.security import LoginLimiter

    client, platform = web()
    platform.login_limiter = LoginLimiter(max_failures=100)  # as if each guess came from a new address
    platform.account_limiter = LoginLimiter(max_failures=3)
    for _ in range(3):
        assert client.post("/api/auth/login", json={"email": MEMBER_EMAIL, "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": MEMBER_EMAIL, "password": PASSWORD}).status_code == 429


def test_unknown_email_still_checks_a_password_hash(web, monkeypatch):
    from gigscout.web import routes_auth

    checked = []
    real = routes_auth.verify_password
    monkeypatch.setattr(routes_auth, "verify_password", lambda pw, stored: checked.append(stored) or real(pw, stored))
    client, _ = web()
    response = client.post("/api/auth/login", json={"email": "ghost@acme-studio.com", "password": "nope"})
    assert response.status_code == 401
    assert checked and checked[0].startswith("scrypt$")


def test_members_cannot_use_admin_endpoints(web):
    client, _ = web()
    login(client, MEMBER_EMAIL)
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/schedules", json={}).status_code in {403, 422}
    assert client.get("/api/profiles").status_code == 200


def test_run_lifecycle_fills_leads_metrics_and_events(web):
    client, platform = web(reasoner=FakeReasoner(score=0.95))
    login(client)
    profile_id = client.get("/api/profiles").json()[0]["id"]  # seeded from profiles/example.yaml

    queued = client.post("/api/runs", json={"profile_id": profile_id, "mode": "pipeline"})
    assert queued.status_code == 202
    run = wait_for_run(client, queued.json()["id"])

    assert run["status"] == "succeeded" and run["mode"] == "pipeline"
    assert run["new_count"] == 3 and run["match_count"] >= 1
    assert "Client leads for" in run["report"]
    assert any(line.startswith("pipeline:") for line in run["trace"]) or run["trace"] == []

    page = client.get("/api/leads", params={"sort": "score"}).json()
    assert page["total"] >= 2
    top = page["items"][0]
    assert top["score"] is not None and top["pitch"] == "We shipped this before."

    events = [e["type"] for e in client.get("/api/events/recent").json()]
    assert {"run.queued", "run.started", "run.finished"} <= set(events)
    assert "run.step" in events

    overview = client.get("/api/metrics/overview").json()
    assert overview["total_leads"] == 3 and overview["runs_total"] == 1
    analytics = client.get("/api/metrics/analytics", params={"days": 7}).json()
    assert len(analytics["timeseries"]) == 7
    assert sum(b["count"] for b in analytics["score_histogram"]) >= 1
    assert analytics["runs"][0]["status"] == "succeeded"
    assert analytics["competition"][0]["bids"] == 3
    assert client.get("/api/runs").json()[0]["id"] == run["id"]


def test_leads_filter_search_and_pipeline_updates(web, sample_leads):
    client, platform = web()
    platform.service.deps.index.add_new(sample_leads)
    login(client, MEMBER_EMAIL)

    assert client.get("/api/leads", params={"source": "nope"}).json()["total"] == 0
    hits = client.get("/api/leads", params={"q": "django api"}).json()["items"]
    assert hits[0]["lead"]["id"] == "fake:1" and hits[0]["similarity"] is not None

    updated = client.patch("/api/leads/fake:1", json={"status": "contacted", "notes": "Emailed CTO"})
    assert updated.json()["status"] == "contacted"
    assert client.get("/api/leads/fake:1").json()["notes"] == "Emailed CTO"
    assert client.get("/api/leads", params={"status": "contacted"}).json()["total"] == 1
    assert client.patch("/api/leads/nope:1", json={"status": "won"}).status_code == 404
    assert client.patch("/api/leads/fake:1", json={"status": "bogus"}).status_code == 422

    funnel = client.get("/api/metrics/analytics").json()["funnel"]
    assert funnel[1] == {"stage": "contacted", "count": 1}

    answer = client.post("/api/leads/ask", json={"question": "any django work?"}).json()
    assert answer["sources"]


def test_schedules_crud_preview_and_trigger(web):
    client, platform = web()
    login(client)
    profile_id = client.get("/api/profiles").json()[0]["id"]

    assert client.get("/api/schedules/preview", params={"cron": "nope"}).json()["valid"] is False
    preview = client.get("/api/schedules/preview", params={"cron": "0 9 * * 1-5"}).json()
    assert preview["valid"] and len(preview["next_runs"]) == 5

    bad = {"name": "x", "profile_id": profile_id, "cron": "61 * * * *"}
    assert client.post("/api/schedules", json=bad).status_code == 422
    created = client.post("/api/schedules", json={"name": "Weekday mornings", "profile_id": profile_id,
                                                   "cron": "0 9 * * 1-5", "mode": "pipeline"}).json()
    assert created["next_run_at"] is not None
    assert platform.schedules.job_count == 1

    paused = client.put(f"/api/schedules/{created['id']}", json={**created, "enabled": False}).json()
    assert paused["enabled"] is False and paused["next_run_at"] is None
    assert platform.schedules.job_count == 0

    run_id = client.post(f"/api/schedules/{created['id']}/trigger").json()["run_id"]
    run = wait_for_run(client, run_id)
    assert run["trigger"] == "schedule" and run["status"] == "succeeded"
    assert client.get("/api/schedules").json()[0]["last_run_id"] == run_id

    assert client.delete(f"/api/schedules/{created['id']}").status_code == 204
    assert client.get("/api/schedules").json() == []


def test_run_activity_is_streamed_and_kept_for_replay(web):
    client, platform = web(reasoner=FakeReasoner(score=0.95))
    login(client)
    profile_id = client.get("/api/profiles").json()[0]["id"]

    started = client.post("/api/runs", json={"profile_id": profile_id, "mode": "pipeline"}).json()
    run = wait_for_run(client, started["id"])
    activity = client.get(f"/api/runs/{run['id']}/activity").json()

    stages = [e["stage"] for e in activity if e["kind"] == "stage"]
    assert stages[0] == "plan" and stages[-1] == "report"
    assert any(e["kind"] == "found" for e in activity) and any(e["kind"] == "reviewed" for e in activity)
    assert all(e["t"] >= 0 for e in activity)
    assert client.get("/api/runs/nope/activity").status_code == 404
    # streamed live, but kept out of the activity feed history so it cannot flood it
    assert "run.activity" not in {e["type"] for e in client.get("/api/events/recent").json()}


def test_a_running_run_can_be_stopped_and_keeps_what_it_did(web, sample_leads):
    import time

    from tests.conftest import FakeSource

    class SlowSource(FakeSource):
        def fetch(self, queries, limit):
            time.sleep(0.4)
            return super().fetch(queries, limit)

    client, _ = web(sources=[SlowSource("slow", sample_leads), SlowSource("slower", sample_leads)])
    login(client)
    profile_id = client.get("/api/profiles").json()[0]["id"]
    run_id = client.post("/api/runs", json={"profile_id": profile_id, "mode": "pipeline"}).json()["id"]
    deadline = time.monotonic() + 5
    while client.get(f"/api/runs/{run_id}").json()["status"] != "running" and time.monotonic() < deadline:
        time.sleep(0.02)

    stop = client.post(f"/api/runs/{run_id}/cancel")
    run = wait_for_run(client, run_id)

    assert stop.json() == {"status": "stopping"}
    assert run["status"] == "cancelled" and any("stopped" in e for e in run["errors"])
    stages = [e["stage"] for e in client.get(f"/api/runs/{run_id}/activity").json() if e["kind"] == "stage"]
    assert stages and "report" not in stages  # it stopped before finishing
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409  # already over
    assert "run.stop" in [a["action"] for a in client.get("/api/admin/audit").json()]


def test_ask_streams_newline_delimited_events(web):
    import json

    client, platform = web(reasoner=FakeReasoner())
    platform.service.deps.index.add_new(platform.service.deps.sources["fake"]._leads)
    assert client.post("/api/leads/ask/stream", json={"question": "django?"}).status_code == 401
    login(client)

    with client.stream("POST", "/api/leads/ask/stream", json={"question": "django api?", "k": 2}) as response:
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.iter_lines() if line]

    sources = next(e for e in events if e["type"] == "sources")["sources"]
    assert len(sources) == 2 and sources[0]["lead"]["title"]  # full lead views, ready to open
    assert "".join(e["text"] for e in events if e["type"] == "token").startswith("Answer based on 2 leads")
    assert events[-1]["type"] == "done"


def test_profiles_crud_and_run_validation(web):
    client, _ = web()
    login(client)
    created = client.post("/api/profiles", json={"name": "Beta Labs", "skills": ["go"]})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert client.put(f"/api/profiles/{pid}", json={"name": "Beta Labs 2", "skills": ["go", "rust"]}).json()[
        "data"]["skills"] == ["go", "rust"]
    assert client.post("/api/profiles", json={"name": "x", "skills": []}).status_code == 422
    assert client.delete(f"/api/profiles/{pid}").status_code == 204
    assert client.post("/api/runs", json={"profile_id": pid}).status_code == 404


def test_admin_users_guardrails_and_audit(web):
    client, _ = web()
    login(client)
    users = client.get("/api/admin/users").json()
    admin_id = next(u["id"] for u in users if u["role"] == "admin")

    assert client.post("/api/admin/users", json={"email": "new@acme-studio.com", "name": "New", "password": "tiny"}
                       ).status_code == 422
    new = client.post("/api/admin/users", json={"email": "New@Acme-Studio.com", "name": "New", "role": "member",
                                                "password": "a-long-enough-password"}).json()
    assert new["email"] == "new@acme-studio.com"
    assert client.post("/api/admin/users", json={"email": "new@acme-studio.com", "name": "Dup",
                                                 "password": "a-long-enough-password"}).status_code == 409

    assert client.patch(f"/api/admin/users/{admin_id}", json={"role": "member"}).status_code == 409  # last admin
    assert client.patch(f"/api/admin/users/{new['id']}", json={"is_active": False}).json()["is_active"] is False
    assert client.post("/api/auth/login", json={"email": "new@acme-studio.com", "password": "a-long-enough-password"}
                       ).status_code == 401

    actions = [a["action"] for a in client.get("/api/admin/audit").json()]
    assert {"user.create", "user.update", "auth.login"} <= set(actions)


def test_admin_system_settings_and_sources(web):
    client, _ = web(google_ads_webhook_key=SecretStr(KEY), ollama_base_url="http://ops:hunter22@ollama.internal:11434")
    login(client)

    system = client.get("/api/admin/system").json()
    assert system["vector_store"]["leads"] == 0 and system["scheduler"]["running"] is True
    assert system["inbound"]["google_ads_webhook"] is True

    settings = client.get("/api/admin/settings").json()
    assert settings["google_ads_webhook_key"] == "••••••"
    assert settings["ollama_base_url"] == "http://••••@ollama.internal:11434"

    sources = {s["name"]: s for s in client.get("/api/admin/sources").json()}
    assert sources["fake"]["channel"] == "pull" and sources["google_ads"]["enabled"] is True
    test = client.post("/api/admin/sources/fake/test").json()
    assert test["ok"] and test["count"] == 3
    assert client.post("/api/admin/sources/nope/test").status_code == 404


def test_failing_source_shows_up_in_source_health(web):
    from tests.conftest import FakeSource

    client, _ = web(sources=[FakeSource("broken", [], fail=True)])
    login(client)
    profile_id = client.get("/api/profiles").json()[0]["id"]
    wait_for_run(client, client.post("/api/runs", json={"profile_id": profile_id, "mode": "pipeline"}).json()["id"])

    broken = next(s for s in client.get("/api/admin/sources").json() if s["name"] == "broken")
    assert broken["recent_failures"] >= 1 and "source is down" in broken["last_error"]
    assert client.post("/api/admin/sources/broken/test").json()["ok"] is False


def test_google_ads_webhook_stores_once_and_announces(web):
    client, platform = web(google_ads_webhook_key=SecretStr(KEY))

    assert client.post("/webhooks/google-ads", json=form_payload()).json() == {"status": "stored"}
    assert client.post("/webhooks/google-ads", json=form_payload()).json() == {"status": "duplicate"}
    assert client.post("/webhooks/google-ads", json=form_payload(google_key="nope")).status_code == 401
    assert client.post("/webhooks/google-ads", json=form_payload(is_test=True)).json() == {"status": "test_received"}
    assert client.post("/webhooks/google-ads", json={"google_key": KEY}).status_code == 422
    assert [e.type for e in platform.bus.recent()] == ["lead.inbound"]
    assert platform.service.deps.index.count() == 1


def test_google_ads_webhook_disabled_without_key(web):
    client, _ = web()
    assert client.post("/webhooks/google-ads", json=form_payload()).status_code == 404


def test_semantic_map_needs_a_few_leads(web, sample_leads):
    from tests.conftest import make_lead

    client, platform = web()
    login(client)
    assert client.get("/api/metrics/map").json() == []
    platform.service.deps.index.add_new([*sample_leads, make_lead("4", "React dashboard"), make_lead("5", "Go API")])
    points = client.get("/api/metrics/map").json()
    assert len(points) == 5
    assert all(-1 <= p["x"] <= 1 and -1 <= p["y"] <= 1 and -1 <= p["z"] <= 1 for p in points)
