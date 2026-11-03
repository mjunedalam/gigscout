"""Wires the nodes into a LangGraph state machine.

    START → plan_queries ─┬─► fetch_source (×N in parallel) ─► index → retrieve → grade ─┬─► report → END
                          └────────────── (no sources) ──────►┘                          │
              ▲                                                                          │
              └──────────────────────── broaden (too few good leads) ◄──────────────────┘
"""

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from gigscout.activity import Activity
from gigscout.agent.nodes import ScoutDeps, ScoutNodes
from gigscout.agent.state import ScoutState
from gigscout.models import AgencyProfile, ScoutResult

StepListener = Callable[[str], None]  # receives one human-readable progress line per step


def build_graph(deps: ScoutDeps, activity: Activity | None = None):
    nodes = ScoutNodes(deps, activity)
    graph = StateGraph(ScoutState)

    graph.add_node("plan_queries", nodes.plan_queries)
    graph.add_node("fetch_source", nodes.fetch_source)
    graph.add_node("index", nodes.index)
    graph.add_node("retrieve", nodes.retrieve)
    graph.add_node("grade", nodes.grade)
    graph.add_node("report", nodes.report)

    graph.add_edge(START, "plan_queries")
    graph.add_conditional_edges("plan_queries", nodes.route_to_sources, ["fetch_source", "index"])
    graph.add_edge("fetch_source", "index")
    graph.add_edge("index", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", nodes.should_broaden, {"broaden": "plan_queries", "report": "report"})
    graph.add_edge("report", END)
    return graph.compile()


def run_scout(
    deps: ScoutDeps, profile: AgencyProfile, on_step: StepListener | None = None, activity: Activity | None = None
) -> ScoutResult:
    final: dict = {}
    initial = {"profile": profile, "iteration": 0, "new_count": 0}
    for mode, chunk in build_graph(deps, activity).stream(initial, stream_mode=["updates", "values"]):
        if mode == "values":
            final = chunk
        elif on_step is not None:
            for node in chunk:
                on_step(f"pipeline: {node} done")
    return ScoutResult(
        queries=tuple(final.get("queries", [])),
        iterations=final.get("iteration", 0),
        fetched_count=final.get("fetched_count", 0),
        new_count=final.get("new_count", 0),
        errors=tuple(final.get("errors", [])),
        matches=tuple(final.get("scored", [])),
        report=final.get("report", ""),
    )
