"""Lead quality check: scams, warnings and duplicates, and what the agents do with them."""

import pytest

from gigscout import quality
from gigscout.activity import Activity
from gigscout.agent.graph import run_scout
from gigscout.models import AgencyProfile, Budget, Client
from tests.conftest import FakeReasoner, FakeSource, login, make_deps, make_lead

LONG = "We need an experienced team to build and maintain our customer portal with a Django backend."


def labels(lead):
    return {f.label for f in quality.check(lead)}


@pytest.mark.parametrize(("text", "label"), [
    ("Pay a small registration fee to get started", "asks you to pay a fee"),
    ("Payment by gift cards only", "mentions gift cards"),
    ("Please send me bitcoin for the software licence", "asks you to send money"),
    ("We will mail you a check, deposit the check and wire the rest", "fake-cheque pattern"),
])
def test_scam_patterns_are_flagged_as_scams(text, label):
    lead = make_lead("1", "Simple data entry", f"{LONG} {text}")
    assert label in labels(lead) and quality.is_scam(quality.assessed(lead))


@pytest.mark.parametrize(("text", "label"), [
    ("Contact me on WhatsApp to discuss", "asks to talk off the platform"),
    ("Telegram: @fastdev99", "asks to talk off the platform"),
    ("First an unpaid test task, then the real work", "wants unpaid work first"),
    ("Equity only for now", "pays in equity only"),
    ("Email me at boss@gmail.com", "posts personal contact details"),
])
def test_risky_patterns_are_warnings(text, label):
    lead = make_lead("1", "Customer portal", f"{LONG} {text}")
    assert label in labels(lead) and not quality.is_scam(quality.assessed(lead))


def test_ordinary_work_that_mentions_messaging_apps_is_not_flagged():
    for text in ("Build a Telegram bot for order updates", "Integrate the WhatsApp Business API into our CRM",
                 "There is no budget limit for the right team", "Without payment integration for now"):
        assert labels(make_lead("1", "Bot project", f"{LONG} {text}")) == set(), text


def test_thin_posts_and_tiny_budgets_are_warned_about():
    lead = make_lead("1", "Website", "Need site", budget=Budget(maximum=40, currency="USD"))
    assert {"very little detail", "budget under $100"} <= labels(lead)


def test_inbound_enquiries_only_get_the_scam_checks():
    lead = make_lead("1", "Enquiry", "hi, call me on whatsapp +44 7700 900123", kind="inbound")
    assert labels(lead) == set()


def test_the_same_job_on_two_sites_is_marked_a_duplicate(index):
    text = "Build a booking app for a dental clinic with React Native and a Django API, payments and reminders."
    first = make_lead("1", "Dental clinic booking app", text, source="freelancer")
    again = make_lead("2", "Dental clinic booking app (React Native)", text, source="peopleperhour")
    other = make_lead("3", "Logistics dashboard", "Fleet tracking dashboard in Vue with live maps.")
    index.add_new([first])

    stored = {lead.id: lead for lead in index.add_new([again, other])}

    assert stored["peopleperhour:2"].duplicate_of == "freelancer:1"
    assert stored["fake:3"].duplicate_of is None
    repost = make_lead("4", "Dental clinic booking app", text, source="guru")
    assert index.add_new([repost])[0].duplicate_of == "freelancer:1"  # always points at the original


def test_leads_stored_before_the_check_are_checked_once(index):
    text = "Build a booking app for a dental clinic with React Native and a Django API, payments and reminders."
    leads = [make_lead("1", "Dental booking app", text), make_lead("2", "Dental booking app", text),
             make_lead("3", "Data entry", f"{LONG} Pay the registration fee first")]
    index.add_new(leads)
    index._collection.update(ids=[lead.id for lead in leads],  # make them look like they predate the check
                             metadatas=[{"payload": lead.model_dump_json(), "qv": 0} for lead in leads])
    assert all(not index.get(lead.id).quality and not index.get(lead.id).duplicate_of for lead in leads)

    assert index.recheck_quality() == 3
    assert index.recheck_quality() == 0
    assert index.get("fake:2").duplicate_of == "fake:1"
    assert quality.is_scam(index.get("fake:3"))


def test_runs_never_spend_the_agents_on_scams_duplicates_or_low_budgets(settings, index):
    profile = AgencyProfile(name="Acme", pitch="Django APIs in Python", skills=("python", "django"),
                            min_budget_usd=1000)
    good = make_lead("good", "Django API for a clinic", f"{LONG} python django", budget=Budget(maximum=5000,
                                                                                             currency="USD"))
    scam = make_lead("scam", "Django API work", f"{LONG} python django. Pay the registration fee to start")
    cheap = make_lead("cheap", "Django API fix", f"{LONG} python django", budget=Budget(maximum=200, currency="USD"),
                      client=Client(name="Tiny"))
    reasoner, events = FakeReasoner(), []
    deps = make_deps(settings, index, [FakeSource("fake", [good, scam, cheap])], reasoner=reasoner)

    result = run_scout(deps, profile, activity=Activity(events.append, profile=profile))

    assert reasoner.graded == ["fake:good"]  # the LLM only judged the lead worth judging
    assert [m.lead.id for m in result.matches] == ["fake:good"]
    reasons = {e["lead"]["id"]: e["reason"] for e in events if e["kind"] == "reviewed" and not e["qualified"]}
    assert reasons == {"fake:scam": "looks like a scam", "fake:cheap": "budget too low"}


def test_the_leads_list_can_hide_or_show_flagged_leads(web):
    client, platform = web()
    platform.index_for(1).add_new([make_lead("ok", "Customer portal", LONG),
                                   make_lead("bad", "Portal", f"{LONG} Pay the registration fee")])
    login(client)

    def ids(q):
        return {v["lead"]["id"] for v in client.get("/api/leads", params={"quality": q}).json()["items"]}

    assert ids("clean") == {"fake:ok"} and ids("flagged") == {"fake:bad"} and len(ids("all")) == 2
    bad = client.get("/api/leads/fake:bad").json()["lead"]
    assert bad["quality"] == [{"code": "scam", "label": "asks you to pay a fee", "severity": "scam"}]
