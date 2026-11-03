import httpx
import pytest
import respx

from gigscout import http as http_module
from gigscout.http import DisallowedByRobots, PoliteClient


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(http_module.time, "sleep", lambda _s: None)


@respx.mock
def test_refuses_urls_disallowed_by_robots(settings):
    respx.get("https://site.example/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private")
    )
    client = PoliteClient(settings)

    with pytest.raises(DisallowedByRobots):
        client.get("https://site.example/private/jobs")


@respx.mock
def test_retries_transient_errors_then_succeeds(settings):
    respx.get("https://site.example/robots.txt").mock(return_value=httpx.Response(404))
    route = respx.get("https://site.example/api").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )

    assert PoliteClient(settings).get_json("https://site.example/api") == {"ok": True}
    assert route.call_count == 2


@respx.mock
def test_raises_after_exhausting_retries(settings):
    respx.get("https://site.example/robots.txt").mock(side_effect=httpx.ConnectError("down"))
    respx.get("https://site.example/api").mock(return_value=httpx.Response(429))

    with pytest.raises(httpx.HTTPStatusError):
        PoliteClient(settings).get("https://site.example/api")


@respx.mock
def test_sends_identifying_user_agent(settings):
    respx.get("https://site.example/robots.txt").mock(return_value=httpx.Response(404))
    route = respx.get("https://site.example/feed").mock(return_value=httpx.Response(200, text="hi"))
    client = PoliteClient(settings)

    assert client.get_text("https://site.example/feed") == "hi"
    assert route.calls.last.request.headers["user-agent"] == settings.user_agent
    client.close()
