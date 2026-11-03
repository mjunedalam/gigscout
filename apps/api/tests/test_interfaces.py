"""RAG, profile loading and MLflow tracking."""

import mlflow
import pytest

from gigscout.profile_loader import ProfileError, load_profile
from gigscout.rag import ask
from gigscout.service import ScoutService
from tests.conftest import FakeReasoner, FakeSource, make_deps


def test_rag_answers_with_retrieved_context(index, sample_leads):
    index.add_new(sample_leads)

    answer = ask("django api work?", index, FakeReasoner(), k=2)

    assert answer.text.startswith("Answer based on 2 leads")
    assert len(answer.sources) == 2


def test_rag_without_llm_or_data(index, sample_leads):
    assert "No leads indexed" in ask("q", index, FakeReasoner()).text
    index.add_new(sample_leads)
    assert "No LLM available" in ask("python", index, None).text


def test_load_profile_validates(tmp_path):
    good = tmp_path / "p.yaml"
    good.write_text("skills: [python]\nmin_budget_usd: 100\n")
    assert load_profile(good).skills == ("python",)

    bad = tmp_path / "bad.yaml"
    bad.write_text("skills: []\n")
    with pytest.raises(ProfileError, match="not a valid agency profile"):
        load_profile(bad)
    with pytest.raises(ProfileError, match="not found"):
        load_profile(tmp_path / "missing.yaml")


def test_example_profile_is_valid():
    profile = load_profile(__import__("pathlib").Path("profiles/example.yaml"))
    assert profile.name == "Acme Software Studio"
    assert "inbound" in profile.kinds


def test_scout_run_is_tracked_in_mlflow(settings, index, profile, sample_leads, tmp_path):
    tracked = settings.model_copy(update={
        "mlflow_enabled": True, "mlflow_tracking_uri": f"sqlite:///{tmp_path}/mlflow.db",
    })
    service = ScoutService(make_deps(tracked, index, [FakeSource("fake", sample_leads)]))

    service.scout(profile)

    run = mlflow.search_runs(experiment_names=[tracked.mlflow_experiment], output_format="list")[0]
    assert run.data.metrics["new_count"] == 3
    assert run.data.params["agency"] == "tester"
    artifacts = {a.path for a in mlflow.MlflowClient().list_artifacts(run.info.run_id)}
    assert {"report.md", "matches.json", "run_details.json"} <= artifacts
