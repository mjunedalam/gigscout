"""Custom website connectors: URL safety, probing a site, and reading leads from feeds or plain pages."""

import httpx
import pytest
import respx

from gigscout.http import DisallowedByRobots, PoliteClient
from gigscout.sources.website import UnsafeUrl, WebsiteSource, check_url, probe, slugify

PUBLIC = {"jobs.example.com": "93.184.216.34", "feeds.example.com": "93.184.216.35"}


def resolver(host: str) -> list[str]:
    known = {**PUBLIC, "localhost": "127.0.0.1", "internal.example.com": "10.0.0.7",
             "metadata.example.com": "169.254.169.254"}
    return [known[host]] if host in known else []


@pytest.fixture
def client(settings):
    c = PoliteClient(settings)
    yield c
    c.close()


@pytest.mark.parametrize("url", [
    "ftp://jobs.example.com/x",
    "http://localhost:8000/admin",
    "http://127.0.0.1/",
    "https://internal.example.com/jobs",
    "http://metadata.example.com/latest/meta-data",
    "https://user:secret@jobs.example.com/",
    "https://unknown-host.example.com/",
    "not a url",
])
def test_check_url_refuses_anything_that_is_not_a_public_web_address(url):
    with pytest.raises(UnsafeUrl):
        check_url(url, resolve=resolver)


def test_check_url_normalises_a_public_address():
    assert check_url("  https://Jobs.Example.com/board  ", resolve=resolver) == "https://jobs.example.com/board"


def test_slugify_makes_a_source_name():
    assert slugify("Acme Jobs Board!") == "acme-jobs-board"


@respx.mock
def test_probe_refuses_a_site_whose_robots_txt_disallows_us(client):
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /")
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=robots)

    with pytest.raises(DisallowedByRobots):
        probe(client, "https://jobs.example.com/board", resolve=resolver)


@respx.mock
def test_probe_prefers_a_feed_the_page_advertises(client):
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example.com/board").mock(return_value=httpx.Response(200, html=(
        '<html><head><title>Acme Jobs</title>'
        '<link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>')))

    site = probe(client, "https://jobs.example.com/board", resolve=resolver)

    assert site.kind == "feed" and site.feed_url == "https://jobs.example.com/feed.xml" and site.title == "Acme Jobs"


@respx.mock
def test_probe_picks_the_feed_that_belongs_to_the_page_not_the_first_one(client):
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example.com/careers/").mock(return_value=httpx.Response(200, html=(
        '<html><head>'
        '<link rel="alternate" type="application/rss+xml" title="Blog" href="https://feeds.example.com/blog.rss">'
        '<link rel="alternate" type="application/rss+xml" title="News" href="/news/rss">'
        '<link rel="alternate" type="application/rss+xml" title="Jobs" href="/careers/feed/rss/">'
        '</head></html>')))

    site = probe(client, "https://jobs.example.com/careers/", resolve=resolver)

    assert site.feed_url == "https://jobs.example.com/careers/feed/rss/"


@respx.mock
def test_preview_lists_what_a_site_offers_without_filtering(client):
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example.com/board").mock(return_value=httpx.Response(200, html=LISTING))
    source = WebsiteSource(client, "acme", "https://jobs.example.com/board", "page", resolve=resolver)

    assert len(source.preview(10)) == 2  # both postings, whatever the query


@respx.mock
def test_probe_falls_back_to_reading_the_page(client):
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=httpx.Response(404))
    page = httpx.Response(200, html="<html><body>Hi</body></html>")
    respx.get("https://jobs.example.com/board").mock(return_value=page)

    assert probe(client, "https://jobs.example.com/board", resolve=resolver).kind == "page"


LISTING = """<html><body>
<nav><a href="/">Home</a><a href="/about">About us</a></nav>
<ul>
  <li><a href="/p/1">Build a Django REST API for a fintech startup</a><p>Python, Django, Postgres. Budget $5k.</p></li>
  <li><a href="https://jobs.example.com/p/2">Logo design for a bakery brand refresh</a><p>Illustrator work.</p></li>
  <li><a href="/p/1">Build a Django REST API for a fintech startup</a></li>
</ul></body></html>"""


@respx.mock
def test_page_source_turns_listing_links_into_leads_matching_the_queries(client):
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example.com/board").mock(return_value=httpx.Response(200, html=LISTING))
    source = WebsiteSource(client, "acme", "https://jobs.example.com/board", "page", resolve=resolver)

    leads = source.fetch(["django"], limit=10)

    assert [lead.title for lead in leads] == ["Build a Django REST API for a fintech startup"]
    lead = leads[0]
    assert lead.source == "acme" and lead.url == "https://jobs.example.com/p/1" and "Postgres" in lead.description
    assert lead.id.startswith("acme:")


@respx.mock
def test_feed_source_reads_entries(client):
    feed = """<?xml version="1.0"?><rss version="2.0"><channel><title>J</title>
    <item><title>Django API contract</title><link>https://feeds.example.com/1</link><description>python</description></item>
    </channel></rss>"""
    respx.get("https://feeds.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://feeds.example.com/rss").mock(return_value=httpx.Response(200, text=feed))
    source = WebsiteSource(client, "feedy", "https://feeds.example.com/", "feed",
                           feed_url="https://feeds.example.com/rss", resolve=resolver)

    assert [lead.title for lead in source.fetch(["django"], 5)] == ["Django API contract"]


@respx.mock
def test_a_redirect_to_an_internal_address_is_refused(client):
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example.com/board").mock(
        return_value=httpx.Response(302, headers={"Location": "https://internal.example.com/secret"}))
    respx.get("https://internal.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://internal.example.com/secret").mock(return_value=httpx.Response(200, html=LISTING))
    source = WebsiteSource(client, "acme", "https://jobs.example.com/board", "page", resolve=resolver)

    with pytest.raises(UnsafeUrl):
        source.fetch(["django"], 5)


def test_connections_are_pinned_to_public_addresses_even_if_dns_changes_after_the_check(settings):
    """DNS rebinding: a name that passed check_url may resolve to an internal IP when the socket opens."""
    import httpcore

    from gigscout.sources.website import PublicOnlyBackend, public_only_transport

    rebinding = {"rebind.example.com": ["10.0.0.9"]}.get
    with pytest.raises(httpcore.ConnectError, match="not a public website"):
        PublicOnlyBackend(lambda h: rebinding(h) or []).connect_tcp("rebind.example.com", 80)

    client = PoliteClient(settings, transport=public_only_transport(lambda h: rebinding(h) or []))
    with pytest.raises(httpx.ConnectError):  # robots.txt and the page itself both go through the pinned transport
        client.get("http://rebind.example.com/jobs")
    client.close()


LEAKY_FEED = '<?xml version="1.0"?><rss version="2.0"><channel><item><title>LEAKED</title></item></channel></rss>'


@respx.mock
def test_a_body_that_looks_like_a_file_path_is_never_read_from_disk(client, tmp_path):
    """feedparser opens str input that looks like a path or URL; bodies must be parsed as bytes."""
    secret = tmp_path / "secret.xml"
    secret.write_text(LEAKY_FEED)
    respx.get("https://jobs.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example.com/board").mock(return_value=httpx.Response(200, text=str(secret)))

    site = probe(client, "https://jobs.example.com/board", resolve=resolver)

    assert site.kind == "page"  # the path was treated as content, not opened
    feed = WebsiteSource(client, "acme", "https://jobs.example.com/board", "feed", resolve=resolver)
    assert feed.preview(5) == []


@respx.mock
def test_rss_source_never_reads_a_local_path_returned_as_the_body(client, tmp_path):
    from gigscout.sources.rss import RssSource

    secret = tmp_path / "secret.xml"
    secret.write_text(LEAKY_FEED)
    respx.get("https://feeds.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://feeds.example.com/rss").mock(return_value=httpx.Response(200, text=str(secret)))

    assert RssSource(client, "rss", ["https://feeds.example.com/rss"]).fetch(["leaked"], 5) == []
