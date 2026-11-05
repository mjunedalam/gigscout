"""The reply copilot: replies are read, the lead moves, and an answer waits for approval."""

from email.message import EmailMessage

import pytest

from gigscout import outreach as outreach_module
from gigscout import replies
from gigscout.models import AgencyProfile
from gigscout.platform.inbox import Incoming, parse_email
from gigscout.platform.tables import LeadEvent, LeadState, Outreach
from tests.conftest import MEMBER_EMAIL, login, make_lead
from tests.test_pitches import AUTOPILOT, desk, pending, scout  # noqa: F401  (desk is a fixture)

PROFILE = AgencyProfile(name="Acme Studio", company_type="Software agency", services=("Django",))


@pytest.mark.parametrize(("text", "intent"), [
    ("Sounds good, can we do a call on Thursday?", "meeting"),
    ("No thanks, we've already hired someone.", "not_interested"),
    ("I am out of the office until Monday with limited access to email.", "out_of_office"),
    ("Please remove me from your list.", "unsubscribe"),
    ("How much would the MVP cost?", "question"),
    ("Maybe later, we're on hold until next quarter.", "not_now"),
    ("Interested. Send me more details.", "interested"),
])
def test_rules_read_the_meaning_of_a_reply(text, intent):
    assert replies.rule_read(text).intent == intent


def test_a_call_request_is_a_meeting_even_if_the_ai_says_interested():
    class Reader:
        def read_reply(self, *_args):
            return replies.ReplyRead(intent="interested", summary="Wants to talk")

    lead = make_lead("1", "Clinic portal", "a portal")
    read, by = replies.read_reply(PROFILE, lead, "orig", "Could we do a quick call on Thursday?", Reader())
    assert (read.intent, by) == ("meeting", "ai")
    read, _ = replies.read_reply(PROFILE, lead, "orig", "Sounds great, send more details.", Reader())
    assert read.intent == "interested"


def test_only_the_clients_own_words_are_read():
    reply = ("Yes, let's talk.\n\nOn Tue, 3 Nov 2026 at 10:00, Acme <hi@acme.com> wrote:\n> We build SaaS.\n"
             "> Interested in a call?")
    assert replies.strip_quoted(reply) == "Yes, let's talk."
    assert replies.rule_read("> no thanks\nCall me tomorrow").intent == "meeting"


def test_answers_fall_back_to_templates_and_never_answer_a_no():
    lead = make_lead("1", "Clinic portal", "a portal")
    meeting = replies.draft_answer(PROFILE, lead, "orig", "call?", "meeting", "cto@clinic.com", "Your portal", None)
    assert meeting.channel == "email" and meeting.subject == "Re: Your portal" and "- " in meeting.body
    bid = replies.draft_answer(PROFILE, lead, "orig", "price?", "question", None, "x", None)
    assert bid.channel == "bid" and bid.subject == ""
    assert "not_interested" in replies.NO_ANSWER and "unsubscribe" in replies.NO_ANSWER


def test_parse_email_keeps_thread_headers_and_plain_text():
    message = EmailMessage()
    message["From"] = "Anna <anna@clinic.com>"
    message["Subject"] = "Re: Your portal"
    message["Message-ID"] = "<r1@clinic.com>"
    message["In-Reply-To"] = "<m1@acme.com>"
    message["References"] = "<m0@acme.com> <m1@acme.com>"
    message.set_content("Let's have a call.\n\n> old text")
    incoming = parse_email(message.as_bytes())
    assert incoming.from_address == "anna@clinic.com" and incoming.message_id == "<r1@clinic.com>"
    assert "<m1@acme.com>" in incoming.in_reply_to and incoming.body.startswith("Let's have a call.")


def _sent_bid(client) -> dict:
    client.put("/api/pitches/settings", json=AUTOPILOT)
    scout(client)
    item = pending(client)[0]["outreach"]
    sent = client.post(f"/api/outreach/{item['id']}/send", json={"channel": "bid", "to": None, "subject": "",
                                                                  "body": item["body"]})
    assert sent.status_code == 200
    return sent.json()


def test_a_pasted_reply_moves_the_lead_and_drafts_an_answer_for_approval(desk):  # noqa: F811
    client, platform = desk
    sent = _sent_bid(client)
    reply = client.post("/api/replies", json={"outreach_id": sent["id"], "body": "Great, can we jump on a call?"})
    assert reply.status_code == 201
    r = reply.json()
    assert r["intent"] == "meeting" and r["read_by"] == "ai" and r["source"] == "pasted" and r["answer_id"]

    inbox = client.get("/api/replies").json()["items"]
    assert inbox[0]["original"]["status"] == "replied" and inbox[0]["answer"]["kind"] == "answer"
    assert inbox[0]["answer"]["body"].startswith("AI answer (meeting)")
    assert client.get("/api/replies/summary").json()["open"] == 1
    with platform.sessions() as session:
        assert session.get(LeadState, (1, sent["lead_id"])).status == "proposal"  # a meeting means in talks
        stages = {e.stage for e in session.query(LeadEvent).filter_by(lead_id=sent["lead_id"])}
        assert {"replied", "proposal"} <= stages

    answer = inbox[0]["answer"]
    assert any(i["outreach"]["id"] == answer["id"] for i in pending(client))  # waits with the other pitches
    approved = client.post(f"/api/outreach/{answer['id']}/send", json={"channel": "bid", "to": None, "subject": "",
                                                                       "body": answer["body"]})
    assert approved.status_code == 200
    assert client.get("/api/replies/summary").json()["open"] == 0  # answering handled it
    assert client.get("/api/replies", params={"state": "handled"}).json()["items"][0]["reply"]["handled_by"]


def test_a_no_closes_the_lead_without_an_answer(desk):  # noqa: F811
    client, platform = desk
    sent = _sent_bid(client)
    r = client.post("/api/replies", json={"outreach_id": sent["id"], "body": "No thanks, not for us."}).json()
    assert r["intent"] == "not_interested" and r["answer_id"] is None
    with platform.sessions() as session:
        assert session.get(LeadState, (1, sent["lead_id"])).status == "lost"
    assert client.post(f"/api/replies/{r['id']}/done").json()["handled_at"]


def test_mailbox_replies_match_by_thread_and_are_taken_in_once(desk, monkeypatch):  # noqa: F811
    client, platform = desk
    client.put("/api/pitches/settings", json=AUTOPILOT)
    scout(client)
    item = pending(client)[0]["outreach"]
    monkeypatch.setattr(platform.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(platform.settings, "smtp_from", "Acme <hi@acme.com>")
    monkeypatch.setattr(outreach_module, "send_email", lambda *a, **k: "<sent-1@acme.com>")
    sent = client.post(f"/api/outreach/{item['id']}/send", json={
        "channel": "email", "to": "cto@client.com", "subject": "Your project", "body": item["body"]}).json()

    incoming = Incoming("cto@client.com", "Re: Your project", "How much would this cost?", "<r1@client.com>",
                        ("<sent-1@acme.com>",), authenticated=True)
    match = platform.replies.match(incoming)
    assert match is not None and match.id == sent["id"]
    by_sender = platform.replies.match(Incoming("CTO@client.com", "Hi", "x", "<r2@client.com>", (), True))
    assert by_sender is not None and by_sender.id == sent["id"]
    forged = Incoming("cto@client.com", "Hi", "x", "<r2b@client.com>", (), authenticated=False)
    assert platform.replies.match(forged) is None  # a From address alone proves nothing
    assert platform.replies.match(Incoming("stranger@else.com", "Hi", "x", "<r3@x>", (), True)) is None

    monkeypatch.setattr("gigscout.platform.inbox.imap_ready", lambda _s: True)
    monkeypatch.setattr("gigscout.platform.inbox.fetch_recent", lambda _s: [incoming, incoming])
    assert platform.replies.poll() == 1  # the same email twice is taken in once
    answer = client.get("/api/replies").json()["items"][0]["answer"]
    assert answer["channel"] == "email" and answer["to"] == "cto@client.com"
    with platform.sessions() as session:
        assert session.get(Outreach, answer["id"]).in_reply_to == "<r1@client.com>"  # the answer joins the thread


def test_viewers_cannot_paste_and_other_workspaces_cannot_see(desk):  # noqa: F811
    client, _ = desk
    sent = _sent_bid(client)
    assert client.post("/api/replies", json={"outreach_id": 99999, "body": "hello"}).status_code == 404
    login(client, MEMBER_EMAIL)
    assert client.post("/api/replies", json={"outreach_id": sent["id"], "body": "Call me?"}).status_code == 201
    assert client.post("/api/replies/check-mailbox").status_code == 403  # members cannot trigger mailbox reads


def _signed(from_domain: str, results: str) -> bytes:
    message = EmailMessage()
    message["Authentication-Results"] = results
    message["Authentication-Results"] = "attacker.example; dmarc=pass header.from=" + from_domain  # a forged one
    message["From"] = f"CTO <cto@{from_domain}>"
    message["Message-ID"] = "<x@y>"
    message.set_content("No thanks.")
    return message.as_bytes()


def test_only_our_servers_authentication_result_counts():
    ok = parse_email(_signed("client.com", "mx.google.com; dkim=pass header.i=@client.com; dmarc=pass "
                                           "(p=REJECT) header.from=client.com"))
    assert ok.authenticated
    dkim_only = parse_email(_signed("mail.client.com", "mx.google.com; dkim=pass header.d=client.com"))
    assert dkim_only.authenticated  # signed by the parent domain
    failed = parse_email(_signed("client.com", "mx.google.com; dkim=fail header.i=@client.com; dmarc=fail"))
    assert not failed.authenticated  # the second, forged header is ignored
    other = parse_email(_signed("client.com", "mx.google.com; dkim=pass header.i=@evil.com"))
    assert not other.authenticated


def test_an_unverified_reply_is_kept_and_answered_but_moves_nothing(desk):  # noqa: F811
    client, platform = desk
    sent = _sent_bid(client)
    reply = platform.replies.receive(1, sent["id"], "No thanks, not for us.", "cto@client.com", "Re", "<f1@x>",
                                     verified=False)
    assert reply is not None and reply.verified is False
    with platform.sessions() as session:
        assert session.get(LeadState, (1, sent["lead_id"])).status == "contacted"  # not marked lost
        assert session.get(Outreach, sent["id"]).status == "sent"
    item = client.get("/api/replies").json()["items"][0]["reply"]
    assert item["verified"] is False and item["intent"] == "not_interested"


def test_the_sender_fallback_never_guesses_between_workspaces(desk, monkeypatch):  # noqa: F811
    client, platform = desk
    from gigscout.platform.tables import Workspace, utcnow
    with platform.sessions() as session:
        session.add(Workspace(id=2, name="Other agency", form_key="other-agency-form-key"))
        session.flush()
        for ws in (1, 2):
            session.add(Outreach(workspace_id=ws, lead_id=f"x:{ws}", channel="email", to_address="cto@shared.com",
                                 status="sent", sent_at=utcnow(), created_by="a"))
        session.commit()
    assert platform.replies.match(Incoming("cto@shared.com", "Hi", "x", "<s1@x>", (), True)) is None
