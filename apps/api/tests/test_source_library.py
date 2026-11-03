"""The source library: checked public websites per company type, added in one click."""

from urllib.parse import urlsplit

from gigscout.profile_templates import TEMPLATES
from gigscout.source_library import LIBRARY, for_company_type
from tests.conftest import login


def test_every_library_source_is_a_public_https_site_for_known_company_types():
    types = {t.company_type for t in TEMPLATES}
    assert len(LIBRARY) >= 15
    for entry in LIBRARY:
        assert urlsplit(entry.url).scheme == "https" and entry.company_types <= types, entry.name
        assert entry.lead_kind in {"project", "contract", "hiring"}
    assert len({e.url for e in LIBRARY}) == len(LIBRARY)


def test_every_company_type_has_somewhere_to_look():
    for template in TEMPLATES:
        assert for_company_type(template.company_type), template.company_type


def test_library_is_matched_loosely_to_what_the_company_typed():
    names = {e.name for e in for_company_type("UK construction firm")}
    assert "GOV.UK Find a Tender" in names


def test_library_endpoint_marks_sites_already_connected(web, monkeypatch):
    from gigscout.sources.website import SiteProbe
    from gigscout.web import routes_admin

    monkeypatch.setattr(routes_admin, "probe", lambda client, url: SiteProbe("feed", url, "x", url))
    client, platform = web()
    login(client)
    design = client.get("/api/admin/connectors/library", params={"company_type": "Design studio"}).json()
    dribbble = next(e for e in design if e["name"] == "Dribbble jobs")
    assert dribbble["added"] is False and dribbble["lead_kind"] == "hiring"

    added = client.post("/api/admin/connectors", json={"name": dribbble["name"], "url": dribbble["url"],
                                                       "lead_kind": dribbble["lead_kind"]})
    assert added.status_code == 201 and added.json()["lead_kind"] == "hiring"
    again = client.get("/api/admin/connectors/library", params={"company_type": "Design studio"}).json()
    assert next(e for e in again if e["name"] == "Dribbble jobs")["added"] is True
    assert len(client.get("/api/admin/connectors/library").json()) >= 15  # no filter: everything
