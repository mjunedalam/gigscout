"""OllamaReasoner prompt wiring, with a stub chat model (no Ollama needed)."""

from types import SimpleNamespace

from gigscout.agent.reasoner import OllamaReasoner, QueryPlan, describe_budget, describe_client
from gigscout.models import Budget, Client, LeadAssessment
from tests.conftest import make_lead


class StubLLM:
    """Records every prompt; structured calls return a canned instance of the requested schema."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def with_structured_output(self, schema):
        canned = {
            QueryPlan: QueryPlan(queries=[" SaaS MVP ", "", "Mobile App"]),
            LeadAssessment: LeadAssessment(score=0.8, reasons="fits", pitch="hi"),
        }[schema]
        return SimpleNamespace(invoke=lambda prompt: self._record(prompt, canned))

    def invoke(self, prompt: str):
        return self._record(prompt, SimpleNamespace(content="text"))

    def _record(self, prompt, result):
        self.prompts.append(prompt)
        return result


def test_reasoner_fills_every_prompt(profile):
    llm = StubLLM()
    reasoner = OllamaReasoner(llm)
    lead = make_lead("1", "Booking app", client=Client(name="Clinic", country="Canada", email="a@b.c"), bid_count=4)

    assert reasoner.plan_queries(profile, previous=["django api"]) == ["saas mvp", "mobile app"]
    assert reasoner.qualify(profile, lead).pitch == "hi"
    assert reasoner.summarize(profile, "| table |") == "text"
    assert reasoner.answer("q?", "[1] lead") == "text"

    plan, qualify, *_ = llm.prompts
    assert "too few good leads: django api" in plan
    assert "Client: Clinic, Canada" in qualify and "Competing bids: 4" in qualify
    assert "a@b.c" not in qualify  # contact details never reach the LLM


def test_describe_helpers():
    assert describe_budget(make_lead("1", "x")) == "not stated"
    budgeted = make_lead("2", "x", budget=Budget(minimum=1, maximum=2, currency="USD"))
    assert describe_budget(budgeted) == "1.0-2.0 USD (unknown)"
    assert describe_client(make_lead("3", "x")) == "unknown"
    assert describe_client(make_lead("4", "x", client=Client(email="only@mail"))) == "unknown"
