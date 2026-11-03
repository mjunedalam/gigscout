"""MLflow experiment tracking ("the flight recorder"): params, metrics, artifacts and LangGraph traces per run."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from gigscout.config import Settings
from gigscout.models import AgencyProfile, ScoutResult

log = logging.getLogger(__name__)


class RunLogger:
    def __init__(self, active: bool) -> None:
        self._active = active
        self._started = time.monotonic()

    def log_result(self, result: ScoutResult) -> None:
        if not self._active:
            return
        import mlflow

        scores = [m.score for m in result.matches]
        mlflow.log_metrics({
            "fetched_count": result.fetched_count,
            "new_count": result.new_count,
            "match_count": len(result.matches),
            "inbound_count": sum(1 for m in result.matches if m.lead.kind == "inbound"),
            "top_score": max(scores, default=0.0),
            "mean_top5_score": sum(scores[:5]) / len(scores[:5]) if scores else 0.0,
            "iterations": result.iterations,
            "error_count": len(result.errors),
            "duration_seconds": time.monotonic() - self._started,
        })
        mlflow.log_dict(
            {"queries": list(result.queries), "errors": list(result.errors), "trace": list(result.trace)},
            "run_details.json",
        )
        mlflow.log_dict(
            {"matches": [m.model_dump(mode="json") for m in result.matches]}, "matches.json"
        )
        mlflow.log_text(result.report, "report.md")


@contextmanager
def tracked_run(settings: Settings, profile: AgencyProfile, mode: str = "pipeline") -> Iterator[RunLogger]:
    if not settings.mlflow_enabled:
        yield RunLogger(active=False)
        return
    import mlflow

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    mlflow.langchain.autolog()  # traces every LangGraph node and LLM call
    with mlflow.start_run(run_name=f"scout-{profile.name}"[:200]):
        mlflow.log_params({
            "mode": mode,
            "agency": profile.name,
            "lead_kinds": ",".join(profile.kinds),
            "skills": ",".join(profile.skills)[:500],
            "min_budget_usd": profile.min_budget_usd,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "top_k": settings.top_k,
            "good_match_threshold": settings.good_match_threshold,
            "max_iterations": settings.max_iterations,
        })
        yield RunLogger(active=True)
