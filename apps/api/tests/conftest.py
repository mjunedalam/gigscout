import hashlib
import math
import os
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from gigscout.agent.nodes import ScoutDeps
from gigscout.config import Settings
from gigscout.models import AgencyProfile, Budget, Lead, LeadAssessment, OutreachText, ProfileSuggestion
from gigscout.replies import ReplyRead
from gigscout.research import ResearchBrief
from gigscout.store.vector_store import LeadIndex

DIMENSIONS = 128


class FakeEmbedder:
    """Deterministic bag-of-words embedding: texts sharing words end up close together."""

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for word in text.lower().replace(",", " ").split():
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeSource:
    def __init__(self, name: str, leads: list[Lead], fail: bool = False) -> None:
        self.name = name
        self._leads = leads
        self._fail = fail
        self.calls: list[list[str]] = []

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        self.calls.append(list(queries))
        if self._fail:
            raise RuntimeError("source is down")
        return list(self._leads)


class FakeReasoner:
    def __init__(self, score: float = 0.9, fail_grade: bool = False) -> None:
        self.score = score
        self.fail_grade = fail_grade
        self.graded: list[str] = []

    def plan_queries(self, profile: AgencyProfile, previous: Sequence[str]) -> list[str]:
        return ["llm query"] if not previous else ["broader query"]

    def qualify(self, profile: AgencyProfile, lead: Lead) -> LeadAssessment:
        if self.fail_grade:
            raise RuntimeError("llm timeout")
        self.graded.append(lead.id)
        return LeadAssessment(score=self.score, reasons="LLM says good fit", pitch="We shipped this before.")

    def summarize(self, profile: AgencyProfile, leads: str) -> str:
        return "Briefing: great leads today."

    def answer(self, question: str, context: str) -> str:
        return f"Answer based on {context.count('[')} leads [1]"

    def suggest_profile(self, company_type: str, description: str) -> ProfileSuggestion:
        return ProfileSuggestion(services=[f"{company_type} services"], skills=["specialist"],
                                 keywords=[company_type.lower()], exclude=["unpaid"], industries=[])

    def draft_outreach(self, profile: AgencyProfile, lead: Lead, pitch: str, channel: str,
                       evidence: str = "") -> OutreachText:
        if self.fail_grade:
            raise RuntimeError("llm timeout")
        proof = evidence.split(": ", 1)[1][:200] if evidence.startswith("[1]") else ""
        body = f"AI draft for {lead.title} ({channel}). {proof}".strip()
        return OutreachText(subject=f"About {lead.title}", body=body)

    def read_reply(self, profile: AgencyProfile, lead: Lead, original: str, reply: str) -> ReplyRead:
        if self.fail_grade:
            raise RuntimeError("llm timeout")
        intent = "meeting" if "call" in reply.lower() else "not_interested" if "no thanks" in reply.lower() \
            else "question"
        return ReplyRead(intent=intent, summary=f"AI read: {reply[:60]}")

    def draft_answer(self, profile: AgencyProfile, lead: Lead, original: str, reply: str, intent: str,
                     evidence: str) -> OutreachText:
        return OutreachText(subject="", body=f"AI answer ({intent}) to: {reply[:60]}")

    def research(self, profile: AgencyProfile, lead: Lead, findings: str) -> ResearchBrief:
        site = findings.splitlines()[0].removeprefix("Website: ")
        return ResearchBrief(summary=f"AI brief on {lead.title}", needs=["a web app"], signals=[],
                             talking_points=[f"Mention {site}"], risks=[])

    def answer_stream(self, question: str, context: str):
        yield from ("Answer ", "based ", f"on {context.count('[')} ", "leads [1]")


def make_lead(
    pid: str, title: str, description: str = "", source: str = "fake", skills: tuple[str, ...] = (), **kw
) -> Lead:
    return Lead(
        id=f"{source}:{pid}",
        source=source,
        title=title,
        description=description or title,
        url=f"https://example.com/{pid}",
        skills=skills,
        posted_at=kw.pop("posted_at", datetime.now(UTC)),
        **kw,
    )


@pytest.fixture
def database_url():
    """SQLite by default. With GIGSCOUT_TEST_POSTGRES_URL set (an admin connection, e.g. to the `postgres`
    database), each test gets its own throwaway Postgres database, so the whole suite also runs on Postgres."""
    admin_url = os.environ.get("GIGSCOUT_TEST_POSTGRES_URL")
    if not admin_url:
        yield None
        return
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    name = f"gs_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    yield make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.dispose()


@pytest.fixture
def settings(tmp_path, database_url) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        data_dir=tmp_path / "data",
        llm_provider="none",
        mlflow_enabled=False,
        http_min_interval=0,
        min_good_matches=1,
        good_match_threshold=0.3,
        max_iterations=2,
    )


@pytest.fixture
def index(settings) -> LeadIndex:
    return LeadIndex(settings.chroma_path, "test", FakeEmbedder())


@pytest.fixture
def profile() -> AgencyProfile:
    return AgencyProfile(
        name="tester",
        pitch="Agency building Django APIs in Python",
        skills=("python", "django"),
        keywords=("django api",),
        exclude=("wordpress",),
        min_budget_usd=200,
    )


@pytest.fixture
def sample_leads() -> list[Lead]:
    return [
        make_lead("1", "Build Django REST API", "Need a python django team for an API",
                  skills=("Python", "Django"), budget=Budget(maximum=500, currency="USD"), bid_count=3),
        make_lead("2", "Fix WordPress theme", "wordpress php css tweaks", skills=("PHP",)),
        make_lead("3", "Python scraper for ecommerce", "python scraping with requests"),
    ]


def make_deps(settings, index, sources, reasoner=None) -> ScoutDeps:
    return ScoutDeps(settings=settings, sources={s.name: s for s in sources}, index=index, reasoner=reasoner)


ADMIN_EMAIL, MEMBER_EMAIL, PASSWORD = "admin@acme-studio.com", "rep@acme-studio.com", "correct-horse-battery"


@pytest.fixture
def web(settings, index, sample_leads):
    """A running app (lifespan included) on fakes, with one admin and one member. Yields a builder."""
    from fastapi.testclient import TestClient

    from gigscout.api import create_app
    from gigscout.platform.container import Platform
    from gigscout.platform.security import hash_password
    from gigscout.platform.tables import DEFAULT_WORKSPACE, Membership, User
    from gigscout.service import ScoutService

    clients = []

    def build(sources=None, reasoner=None, **overrides):
        configured = settings.model_copy(update=overrides)
        deps = make_deps(configured, index, sources or [FakeSource("fake", sample_leads)], reasoner)
        platform = Platform.build(configured, ScoutService(deps))
        with platform.sessions() as session:
            for email, role in ((ADMIN_EMAIL, "admin"), (MEMBER_EMAIL, "member")):
                user = User(email=email, name=role.title(), role=role, password_hash=hash_password(PASSWORD))
                session.add(user)
                session.flush()
                session.add(Membership(user_id=user.id, workspace_id=DEFAULT_WORKSPACE,
                                       role="owner" if role == "admin" else "member"))
            session.commit()
        client = TestClient(create_app(lambda: platform))
        client.__enter__()
        clients.append(client)
        return client, platform

    yield build
    for client in clients:
        client.__exit__(None, None, None)


def login(client, email=ADMIN_EMAIL, password=PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response


def wait_for_run(client, run_id: str, timeout: float = 20.0) -> dict:
    """Runs execute on a worker thread; poll until they reach a final state."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in {"succeeded", "failed", "cancelled"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout}s")
