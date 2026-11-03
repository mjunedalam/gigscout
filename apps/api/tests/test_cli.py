import pytest
from typer.testing import CliRunner

from gigscout import cli
from gigscout.service import ScoutService
from tests.conftest import FakeReasoner, FakeSource, make_deps

runner = CliRunner()


@pytest.fixture(autouse=True)
def fake_service(monkeypatch, settings, index, sample_leads):
    service = ScoutService(make_deps(settings, index, [FakeSource("fake", sample_leads)], FakeReasoner()))
    monkeypatch.setattr(cli, "_service", lambda: service)


def test_scout_search_ask_and_sources():
    scout = runner.invoke(cli.app, ["scout", "--profile", "profiles/example.yaml"])
    assert scout.exit_code == 0, scout.output
    assert "Client leads for Acme Software Studio" in scout.output

    assert "Build Django REST API" in runner.invoke(cli.app, ["search", "django api"]).output
    assert "Answer based on" in runner.invoke(cli.app, ["ask", "best django gig?"]).output
    assert "fake" in runner.invoke(cli.app, ["sources"]).output


def test_scout_reports_bad_profile(tmp_path):
    result = runner.invoke(cli.app, ["scout", "--profile", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1
    assert "not found" in result.output
