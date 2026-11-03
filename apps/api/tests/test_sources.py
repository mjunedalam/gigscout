import httpx
import pytest
import respx

from gigscout.http import PoliteClient
from gigscout.sources import freelancer, remoteok, remotive
from gigscout.sources.freelancer import FreelancerSource
from gigscout.sources.registry import build_sources
from gigscout.sources.remoteok import RemoteOkSource
from gigscout.sources.remotive import RemotiveSource
from gigscout.sources.rss import RssSource

FREELANCER_PAYLOAD = {
    "status": "success",
    "result": {"projects": [{
        "id": 42, "title": " Django API ", "seo_url": "python/django-api", "type": "fixed",
        "description": "<p>Build an <b>API</b></p>", "time_submitted": 1793520012,
        "currency": {"code": "GBP", "exchange_rate": 1.3}, "budget": {"minimum": 100, "maximum": 200},
        "jobs": [{"name": "Python"}, {"name": "Django"}], "bid_stats": {"bid_count": 7},
        "location": {"country": {"name": "Canada"}},
    }]},
}
REMOTEOK_PAYLOAD = [
    {"legal": "link back please"},
    {"id": "7", "slug": "py-dev", "position": "Python Developer", "company": "Acme", "tags": ["python"],
     "description": "<p>python backend</p>", "date": "2026-11-01T08:00:12+00:00",
     "url": "https://remoteok.com/remote-jobs/7", "salary_min": 90000, "salary_max": 120000},
    {"id": "8", "position": "Wedding Coordinator", "tags": ["travel"], "description": "weddings"},
]
REMOTIVE_PAYLOAD = {"jobs": [{
    "id": 9, "url": "https://remotive.com/jobs/9", "title": "Contract Django Dev", "company_name": "Beta",
    "tags": ["django"], "job_type": "contract", "publication_date": "2026-11-01T10:00:00",
    "description": "<p>Django work</p>",
}]}
RSS_FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>Jobs</title>
<item><title>Acme: Senior Python Engineer</title><link>https://wwr.example/jobs/1</link>
<description>&lt;p&gt;python and django&lt;/p&gt;</description><pubDate>Sun, 01 Nov 2026 10:00:00 +0000</pubDate></item>
<item><title>Designer</title><link>https://wwr.example/jobs/2</link><description>figma</description></item>
</channel></rss>"""


@pytest.fixture
def client(settings):
    return PoliteClient(settings)


@pytest.fixture(autouse=True)
def no_robots():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*/robots\.txt$").mock(return_value=httpx.Response(404))
        yield mock


def test_freelancer_parses_budget_skills_competition_and_url(client, no_robots):
    no_robots.get(freelancer.API_URL).mock(return_value=httpx.Response(200, json=FREELANCER_PAYLOAD))

    [lead] = FreelancerSource(client).fetch(["django"], limit=5)

    assert lead.id == "freelancer:42"
    assert lead.kind == "project"
    assert lead.title == "Django API"
    assert lead.description == "Build an API"
    assert lead.url == "https://www.freelancer.com/projects/python/django-api"
    assert lead.skills == ("Python", "Django")
    assert lead.budget.max_usd == pytest.approx(260)
    assert lead.posted_at.year == 2026
    assert lead.bid_count == 7
    assert lead.client.country == "Canada"


def test_freelancer_tolerates_hidden_client_details():
    raw = {k: v for k, v in FREELANCER_PAYLOAD["result"]["projects"][0].items() if k not in {"bid_stats", "location"}}
    lead = freelancer.parse({**raw, "location": {"country": {"name": None}}})
    assert lead.client is None and lead.bid_count is None


def test_freelancer_issues_one_request_per_query(client, no_robots):
    route = no_robots.get(freelancer.API_URL).mock(return_value=httpx.Response(200, json=FREELANCER_PAYLOAD))
    FreelancerSource(client).fetch(["a", "b"], limit=5)
    assert route.call_count == 2


def test_remoteok_listings_are_hiring_signals(client, no_robots):
    no_robots.get(remoteok.API_URL).mock(return_value=httpx.Response(200, json=REMOTEOK_PAYLOAD))

    leads = RemoteOkSource(client).fetch(["python"], limit=5)

    assert [lead.id for lead in leads] == ["remoteok:7"]  # legal row skipped, off-topic row filtered
    assert leads[0].kind == "hiring"
    assert leads[0].client.name == "Acme"
    assert leads[0].budget.max_usd == 120000


def test_remotive_marks_contract_roles(client, no_robots):
    no_robots.get(remotive.API_URL).mock(return_value=httpx.Response(200, json=REMOTIVE_PAYLOAD))

    [lead] = RemotiveSource(client).fetch(["django"], limit=5)

    assert lead.kind == "contract"
    assert lead.client.name == "Beta"
    assert lead.posted_at.tzinfo is not None
    assert remotive.parse({**REMOTIVE_PAYLOAD["jobs"][0], "job_type": "full_time"}).kind == "hiring"


def test_rss_filters_entries_and_builds_stable_ids(client, no_robots):
    no_robots.get("https://wwr.example/feed.rss").mock(return_value=httpx.Response(200, text=RSS_FEED))
    source = RssSource(client, "wwr", ["https://wwr.example/feed.rss"])

    first = source.fetch(["python"], limit=5)
    second = source.fetch(["python"], limit=5)

    assert [p.title for p in first] == ["Acme: Senior Python Engineer"]
    assert first[0].id == second[0].id
    assert first[0].description == "python and django"
    assert first[0].kind == "hiring" and first[0].client is None


def test_registry_adds_custom_rss_only_when_configured(settings, client):
    assert "rss" not in build_sources(settings, client)
    custom = settings.model_copy(update={"rss_feeds": ["https://x.example/feed"]})
    sources = build_sources(custom, client)
    assert set(sources) == {"freelancer", "remoteok", "remotive", "weworkremotely", "rss", "contracts_finder",
                            "find_a_tender", "ted"}
    assert sources["rss"]._kind == "project"  # tender/RFP feeds default to client projects
