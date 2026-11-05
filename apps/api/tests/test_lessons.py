"""What gets replies: outcomes become lessons, and the pitch writer is given them."""

from gigscout.platform import lessons
from gigscout.platform.lessons import Outcome
from gigscout.platform.tables import AGENT_AUTHOR, Outreach, utcnow
from tests.test_pitches import AUTOPILOT, desk, pending, scout  # noqa: F401  (desk is a fixture)


def outcome(words=100, replied=False, cites=False, question=True, edited=False, channel="bid") -> Outcome:
    return Outcome(words=words, channel=channel, kind="first", cites_work=cites, by_agents=True, edited=edited,
                   has_question=question, replied=replied)


def test_no_lessons_until_there_is_enough_to_learn_from():
    assert lessons.lessons([outcome(replied=True)] * 9) == []
    assert lessons.lessons([outcome()] * 20) == []  # nobody replied: nothing to compare against


def test_traits_that_get_more_or_fewer_replies_become_lessons():
    data = ([outcome(words=60, cites=True, replied=True)] * 6 + [outcome(words=60, cites=True)] * 2
            + [outcome(words=200, replied=True)] * 1 + [outcome(words=200)] * 9)
    found = {lesson.trait: lesson for lesson in lessons.lessons(data)}
    assert found["citing your past work"].better and found["citing your past work"].replied == 6
    assert found["under 80 words"].lift > 1.8 and not found["over 140 words"].better  # 75% vs 39% usual
    assert "ending on a question" not in found  # every message had one: nothing to compare
    text = lessons.for_drafting(found.values())
    assert text.startswith("- Messages") and "as often" in text


def test_outcomes_read_what_the_message_was_like(web):
    _, platform = web()
    with platform.sessions() as session:
        session.add(Outreach(workspace_id=1, lead_id="x:1", channel="email", status="replied", created_by=AGENT_AUTHOR,
                             body="Short note. Can we talk?\n> quoted old text with many many words here",
                             drafted_body="A different draft", evidence=[{"title": "Case"}], sent_at=utcnow()))
        session.add(Outreach(workspace_id=1, lead_id="x:2", channel="bid", status="draft", created_by="a", body="x"))
        session.add(Outreach(workspace_id=1, lead_id="x:3", channel="bid", status="sent", kind="answer",
                             created_by="a", body="x", sent_at=utcnow()))
        session.commit()
        [o] = lessons.load_outcomes(session, 1)  # drafts and answers to replies are not pitches that went out
    assert (o.words, o.cites_work, o.edited, o.has_question, o.replied) == (5, True, True, True, True)


def test_the_pitch_writer_gets_the_lessons_and_the_report_shows_them(desk):  # noqa: F811
    client, platform = desk
    with platform.sessions() as session:
        for n in range(12):
            session.add(Outreach(workspace_id=1, lead_id=f"old:{n}", channel="bid", created_by=AGENT_AUTHOR,
                                 status="replied" if n < 4 else "sent", sent_at=utcnow(),
                                 body="Short and sweet, can we talk?" if n < 5 else " ".join(["word"] * 200),
                                 drafted_body=None))
        session.commit()
    report = client.get("/api/reports/lessons").json()
    assert report["sent"] == 12 and report["replied"] == 4 and report["lessons"]
    assert any(lesson["trait"] == "under 80 words" and lesson["better"] for lesson in report["lessons"])

    client.put("/api/pitches/settings", json=AUTOPILOT)
    scout(client)
    assert pending(client)
    assert "under 80 words" in platform.service.deps.reasoner.last_lessons
