"""Learning from wins: won and lost leads nudge the scores of similar open leads, with a reason."""

from gigscout.learning import MAX_NUDGE, MIN_OUTCOMES, learn
from gigscout.models import Budget
from gigscout.platform.tables import LeadState
from tests.conftest import login, make_lead


def outcomes():
    """PeoplePerHour leads keep winning; WordPress leads keep losing."""
    won = [make_lead(str(i), f"Django API {i}", source="peopleperhour", skills=("Django",)) for i in range(4)]
    lost = [make_lead(str(i), f"WordPress fix {i}", source="freelancer", skills=("WordPress",),
                      budget=Budget(maximum=300, currency="USD")) for i in range(10, 14)]
    return [(lead, True) for lead in won] + [(lead, False) for lead in lost]


def test_nothing_is_learned_from_too_few_outcomes():
    learning = learn(outcomes()[:3])
    assert not learning.active
    assert learning.nudge(make_lead("x", "Django", source="peopleperhour")) == (0.0, "")


def test_nothing_is_learned_without_both_a_win_and_a_loss():
    assert not learn([(lead, True) for lead, _ in outcomes()]).active


def test_leads_like_past_wins_go_up_and_like_past_losses_go_down():
    learning = learn(outcomes())
    assert learning.active and learning.outcomes == 8 and learning.wins == 4

    up, why_up = learning.nudge(make_lead("n1", "New Django job", source="peopleperhour", skills=("Django",)))
    down, why_down = learning.nudge(make_lead("n2", "WordPress", source="freelancer", skills=("WordPress",)))
    assert 0 < up <= MAX_NUDGE and -MAX_NUDGE <= down < 0
    assert "won 4 of 4" in why_up and "lost 4 of 4" in why_down
    assert learning.nudge(make_lead("n3", "Unrelated", source="somewhere-else")) == (0.0, "")


def test_signals_are_listed_strongest_first_with_plain_labels():
    signals = learn(outcomes()).top_signals()
    assert signals and abs(signals[0].lift) >= abs(signals[-1].lift)
    labels = {s.label for s in signals}
    assert "peopleperhour leads" in labels and "leads asking for wordpress" in labels


def test_marking_leads_won_or_lost_rescores_open_leads(web):
    client, platform = web()
    index = platform.service.deps.index
    past = outcomes()
    fresh = make_lead("open", "Another Django API", source="peopleperhour", skills=("Django",))
    index.add_new([lead for lead, _ in past] + [fresh])
    with platform.sessions() as session:
        session.add(LeadState(lead_id=fresh.id, score=0.5, base_score=0.5))
        for lead, _ in past[:-1]:
            session.add(LeadState(lead_id=lead.id, score=0.6))
        session.commit()
    login(client)
    for lead, won in past[:-1]:
        client.patch(f"/api/leads/{lead.id}", json={"status": "won" if won else "lost"})
    assert client.get(f"/api/leads/{fresh.id}").json()["score"] == 0.5  # 7 outcomes: learning is on, but...

    last, won = past[-1]
    client.patch(f"/api/leads/{last.id}", json={"status": "lost"})
    view = client.get(f"/api/leads/{fresh.id}").json()
    assert view["score"] > 0.5 and view["learned"] > 0 and "won 4 of 4" in view["learned_note"]

    summary = client.get("/api/metrics/learning").json()
    assert summary["active"] and summary["outcomes"] == 8 and summary["needed"] == MIN_OUTCOMES
    assert summary["signals"][0]["label"]


def test_runs_store_both_the_agents_score_and_the_learned_one(web, monkeypatch):
    from gigscout.platform import runs

    class Learned:
        active = True

        def nudge(self, lead):
            return 0.1, "You won 3 of 3 fake leads"

    monkeypatch.setattr(runs, "current_learning", lambda session, index, workspace_id: Learned())
    client, platform = web()
    login(client)
    from tests.conftest import wait_for_run

    profile_id = client.get("/api/profiles").json()[0]["id"]
    started = client.post("/api/runs", json={"profile_id": profile_id, "mode": "pipeline"}).json()
    run = wait_for_run(client, started["id"])
    assert run["status"] == "succeeded"
    with platform.sessions() as session:
        state = next(s for s in session.query(LeadState) if s.base_score is not None)
        assert abs(state.score - min(1.0, state.base_score + 0.1)) < 1e-6 and state.learned_note.startswith("You won")
