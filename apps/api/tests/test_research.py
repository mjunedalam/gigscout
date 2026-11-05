"""The research agent: it finds the client's own site, reads it safely, and briefs the pitch writer."""

from datetime import UTC, datetime

import pytest

from gigscout import research
from gigscout.models import AgencyProfile, Budget, Client
from gigscout.platform.tables import LeadBrief
from gigscout.store.vector_store import StoredLead
from tests.conftest import make_lead
from tests.test_pitches import AUTOPILOT, desk, pending, scout  # noqa: F401  (desk is a fixture)

PROFILE = AgencyProfile(name="Acme Studio", company_type="Software agency", services=("Django",))
HOME = b"""<html><head><title>Clinic Group | Care that fits</title>
<meta name="description" content="Clinic Group runs 12 physiotherapy clinics in London.">
<script src="/_next/static/chunks/main.js"></script><script src="https://js.stripe.com/v3"></script></head>
<body><nav>Menu</nav><h1>Physio near you</h1><p>Book online in two minutes.</p>
<script>ignore me</script></body></html>"""


@pytest.mark.parametrize(("description", "email", "site"), [
    ("We are Distru ( https://www.distru.com/careers ) hiring", None, "https://distru.com"),
    ("Apply on https://www.upwork.com/jobs/1 or https://github.com/x", None, None),
    ("No links here", "cto@clinic-group.co.uk", "https://clinic-group.co.uk"),
    ("No links here", "someone@gmail.com", None),
])
def test_the_clients_own_site_is_found_and_platforms_are_skipped(description, email, site):
    lead = make_lead("1", "Portal", description).model_copy(update={"client": Client(email=email) if email else None})
    assert research.find_website(lead) == site


def test_related_leads_are_other_posts_about_the_same_client():
    lead = make_lead("1", "Portal for Clinic Group", "see https://clinicgroup.com").model_copy(
        update={"client": Client(name="Clinic Group")})
    hiring = make_lead("2", "Clinic Group is hiring a React developer", "join us at clinicgroup.com")
    other = make_lead("3", "Unrelated bakery site", "bread")
    records = [StoredLead(lead=x, seen_at=datetime(2026, 11, 1, tzinfo=UTC)) for x in (lead, hiring, other)]
    assert [r.lead.id for r in research.related_leads(lead, records, "https://clinicgroup.com")] == [hiring.id]


def test_gather_reads_the_site_and_spots_its_technology(monkeypatch):
    pages = []

    def fake_fetch(_client, url):
        pages.append(url)
        if url.endswith("/about"):
            raise ValueError("no page")
        return url, HOME

    monkeypatch.setattr(research, "fetch_public", fake_fetch)
    lead = make_lead("1", "Booking portal", "Clinic Group https://clinicgroup.com needs a portal")
    found = research.gather(object(), lead, [])
    assert found.website == "https://clinicgroup.com" and pages[0] == "https://clinicgroup.com"
    assert found.title.startswith("Clinic Group") and "12 physiotherapy clinics" in found.description
    assert {"Next.js", "React", "Stripe"} <= set(found.tech)
    assert "ignore me" not in found.text and "Book online" in found.text
    assert found.errors == ["https://clinicgroup.com/about: ValueError"]
    rules = research.rule_brief(lead.model_copy(update={"budget": Budget(maximum=9000, currency="USD")}), found)
    assert rules.signals[0] == "Budget up to $9,000" and "Next.js" in rules.talking_points[0]


def test_private_addresses_are_never_fetched(web):
    _, platform = web()
    lead = make_lead("1", "Internal tool", "our admin is at http://127.0.0.1:8000/admin and http://10.0.0.5")
    found = research.gather(platform.service.web_client, lead, [])
    assert found.website == "http://127.0.0.1:8000" and found.text == ""
    assert found.errors and "UnsafeUrl" in found.errors[0]


def test_a_brief_is_written_kept_and_used_by_the_pitch_writer(desk, monkeypatch):  # noqa: F811
    client, platform = desk
    monkeypatch.setattr(research, "fetch_public", lambda _c, url: (url, HOME))
    scout(client)
    lead_id = client.get("/api/leads").json()["items"][0]["lead"]["id"]
    assert client.get(f"/api/research/{lead_id}").json() == {"brief": None}
    made = client.post(f"/api/research/{lead_id}").json()["brief"]
    assert made["made_by"] == "ai" and made["brief"]["summary"].startswith("AI brief on")
    assert client.get(f"/api/research/{lead_id}").json()["brief"]["lead_id"] == lead_id
    assert client.post("/api/research/nope:1").status_code == 404


def test_autopilot_can_research_every_client_before_writing(desk, monkeypatch):  # noqa: F811
    client, platform = desk
    fetched = []
    monkeypatch.setattr(research, "fetch_public", lambda _c, url: fetched.append(url) or (url, HOME))
    assert client.put("/api/pitches/settings", json={**AUTOPILOT, "research_first": True}).json()["research_first"]
    scout(client)
    drafted = {i["outreach"]["lead_id"] for i in pending(client)}
    with platform.sessions() as session:
        briefed = {b.lead_id for b in session.query(LeadBrief).filter_by(workspace_id=1)}
    assert drafted and drafted <= briefed  # every pitch was written after its client was researched
