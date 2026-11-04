"""Under the hood: model calls, tool calls, source fetches and memory searches recorded for the UI."""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from gigscout.activity import HOOD_TEXT_CHARS, MAX_HOOD, Activity
from gigscout.agent.graph import run_scout
from gigscout.hood import HoodRecorder
from gigscout.multiagent.runner import run_team
from tests.conftest import FakeReasoner, FakeSource, make_deps
from tests.test_multiagent import happy_team


def hood(events):
    return [e for e in events if e["kind"] == "hood"]


def test_a_model_call_records_prompt_reply_timing_and_who_asked():
    events = []
    activity = Activity(events.append)
    activity.stage("qualify")
    activity.progress("qualifier", 0, 3, 'checking "Django API"')
    model = GenericFakeChatModel(messages=iter([AIMessage(content="Score 0.8: a strong fit")]))

    model.invoke("Judge this lead: Django API", config={"callbacks": [HoodRecorder(activity)]})

    [event] = hood(events)
    assert event["agent"] == "qualifier" and event["op"] == "llm"
    assert event["title"] == 'Qualifier asked the AI to judge a lead: "Django API"'
    assert event["ms"] >= 0 and event["n"] == 1
    assert event["detail"]["messages"][-1] == {"role": "user", "text": "Judge this lead: Django API"}
    assert event["detail"]["reply"] == "Score 0.8: a strong fit"


def test_a_tool_call_records_its_arguments_and_observation():
    events = []

    @tool
    def search_source(source: str, query: str) -> str:
        """Search a lead source."""
        return f"{source} '{query}': 3 results"

    search_source.invoke({"source": "remotive", "query": "django"},
                         config={"callbacks": [HoodRecorder(Activity(events.append), "prospector")]})

    [event] = hood(events)
    assert event["title"] == "Prospector used a tool to search remotive for 'django'"
    assert event["detail"]["args"] == {"source": "remotive", "query": "django"}
    assert event["detail"]["result"] == "remotive 'django': 3 results"


def test_long_text_is_clipped_and_events_stay_bounded():
    events = []
    activity = Activity(events.append)
    activity.hood("head", "llm", "big", reply="x" * (HOOD_TEXT_CHARS + 50))
    assert hood(events)[0]["detail"]["reply"].endswith("(+50 chars)")
    for _ in range(MAX_HOOD + 10):
        activity.hood("head", "tool", "spam")
    assert len(hood(events)) == MAX_HOOD


def test_pipeline_runs_show_source_fetches_and_memory_searches(settings, index, profile, sample_leads):
    events = []
    deps = make_deps(settings, index, [FakeSource("fake", sample_leads)], reasoner=FakeReasoner())

    run_scout(deps, profile, activity=Activity(events.append, profile=profile))

    ops = {e["op"]: e for e in hood(events)}
    assert ops["fetch"]["agent"] == "prospector" and ops["fetch"]["detail"]["results"] == 3
    assert ops["fetch"]["detail"]["source"] == "fake" and ops["fetch"]["detail"]["sample"]
    assert ops["memory"]["agent"] == "qualifier" and "query" in ops["memory"]["detail"]


def test_team_runs_show_each_agents_model_and_tool_calls(settings, index, profile, sample_leads):
    events = []
    deps = make_deps(settings, index, [FakeSource("fake", sample_leads)])

    run_team(deps, profile, happy_team(), activity=Activity(events.append, profile=profile))

    steps = hood(events)
    assert {e["agent"] for e in steps} == {"head", "prospector", "qualifier", "writer"}
    assert any(e["title"] == "Head of Sales handed the work to the Prospector" for e in steps)
    searches = [e for e in steps if e["op"] == "tool" and e["detail"]["tool"] == "search_source"]
    assert searches and searches[0]["agent"] == "prospector" and "results" in searches[0]["detail"]["result"]
    decided = [e for e in steps if e["op"] == "llm" and e["detail"].get("tool_calls")]
    assert decided and all(e["detail"]["messages"] for e in decided)
    assert [e["n"] for e in steps] == sorted(e["n"] for e in steps)
