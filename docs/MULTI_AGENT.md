# The Multi-Agent Sales Team (ReAct pattern)

GigScout has two ways to run:

| Mode | What runs | Needs an LLM? | Use when |
|---|---|---|---|
| `team` (default when Ollama is up) | A **Head of Sales** ReAct agent directing three **specialist** ReAct agents | Yes (tool calling) | You want the agents to *decide* where to look, which leads to qualify and what to pitch |
| `pipeline` | The fixed LangGraph flow (plan → fetch → index → retrieve → grade → report) | No (the LLM is optional) | Offline, fast, fully predictable runs, e.g. on a cron schedule |

```bash
gigscout scout --mode team --trace     # watch the agents work
gigscout scout --mode pipeline         # the fixed graph
gigscout scout                         # auto: team if an LLM is reachable, else pipeline
```

---

## 1. ReAct: the detective's notebook

**Analogy.** A good detective doesn't solve a case in one go. They loop:

> **Think:** "The butler had keys, so check his alibi."
> **Act:** interview the cook.
> **Observe:** "The cook says the butler was in the kitchen all night."
> **Think:** "Then it wasn't the butler. Check the gardener." …and so on, until they can name the culprit.

**ReAct** (*Reason + Act*) is exactly this loop for an LLM:

```
           ┌──────────────────────────────────────────────┐
           ▼                                              │
  ┌─────────────────┐   tool call   ┌──────────┐  result  │
  │  Reason (LLM)   │──────────────►│ Act      │──────────┘  Observe: the tool's output is
  │ "what next?"    │               │ (a tool) │              added to the conversation
  └─────────────────┘               └──────────┘
           │ no more tool calls
           ▼
     Final answer
```

Unlike the fixed pipeline, the *model* chooses the next step after seeing what the last step
returned. If a source is down, it observes `ERROR: remoteok failed` and tries another. If leads are
thin, it rephrases the query.

**In GigScout.** Every agent is built with LangChain's
[`create_agent`](https://docs.langchain.com/oss/python/langchain/agents), which runs this loop on
a LangGraph graph: a `model` node, a `tools` node, and an edge back to the model until it stops
calling tools.

## 2. Multi-agent: the agency's sales floor

**Analogy.** An agency doesn't have one person do all of sales. The **Head of Sales** doesn't cold-call;
they *assign* work and *check* it:

| Sales floor | GigScout agent (code name) | Its tools (what it can *do*) |
|---|---|---|
| **Head of Sales**: assigns, reviews, decides when the pipeline is ready | Supervisor (`supervisor`) | `delegate_to_scout`, `delegate_to_analyst`, `delegate_to_writer`, `check_progress` |
| **Prospector / SDR**: goes out and finds raw leads | Prospector (`scout`) | `list_sources`, `search_source`, `search_progress` |
| **Qualifier**: decides which leads deserve sales time, spots time-wasters | Qualifier (`analyst`) | `find_leads`, `read_lead`, `qualify_lead`, `view_shortlist` |
| **Outreach Writer**: drafts the briefing and the first messages | Outreach Writer (`writer`) | `view_shortlist`, `read_lead`, `submit_report` |
| **The shared whiteboard** | `RunContext` (the blackboard) | Everyone reads and writes it through their tools |

Why split one agent into four?
- **Focus.** Each specialist has a short prompt and only 3–4 tools, so a small local model
  (8B parameters) is much more reliable than with one giant prompt and 12 tools.
- **Clean context windows.** The Prospector's 25 raw search results never clutter the Writer's
  context. The Head of Sales sees only one-paragraph summaries.
- **Replaceable parts.** Each role can use a different model (`TeamModels`), e.g. a bigger model
  for the Qualifier's judgement and a small fast one for the Prospector.

## 3. How a run actually goes

```
Head of Sales (ReAct)
 ├─ think: "Nothing in memory yet; I need leads."
 ├─ act:   delegate_to_scout("Search for mobile app and SaaS MVP clients…")
 │          └─ Prospector (ReAct)
 │              ├─ list_sources → freelancer, remoteok, remotive, weworkremotely
 │              ├─ search_source(freelancer, "mobile app") → 25 results (9 new)
 │              ├─ search_source(remotive, "react native") → 6 results
 │              └─ answer: "Fetched 31 leads across 2 sources…"
 ├─ observe: summary + "Shared state now: qualified 0/10…"
 ├─ act:   delegate_to_analyst("Qualify the best 10…")
 │          └─ Qualifier (ReAct)
 │              ├─ find_leads("react native booking app") → ids, kinds, heuristic scores
 │              ├─ read_lead("freelancer:40799396") → full description, 4 competing bids
 │              ├─ qualify_lead(id, 0.9, "Exact stack, clear scope", pitch="We shipped a clinic booking app…")
 │              └─ answer: "Qualified 10, including 1 inbound…"
 ├─ act:   delegate_to_writer("Write the briefing…")
 │          └─ Outreach Writer (ReAct): view_shortlist → submit_report(markdown)
 └─ answer: "DONE"
```

See your own run with `gigscout scout --mode team --trace`, or open the **Traces** tab in MLflow
for every prompt, tool call and observation, nested by agent.

## 4. Guardrails: keeping autonomous agents on a leash

Autonomy without limits is how agents loop forever or invent results. The team has hard limits
and safety nets:

| Risk | Guardrail | Setting |
|---|---|---|
| The Prospector hammers the marketplaces | Per-run search budget; duplicate searches refused | `GIGSCOUT_TEAM_MAX_SEARCHES` (12) |
| An agent loops forever | LangGraph recursion limit on each ReAct loop | `TEAM_RECURSION_LIMIT` (30), `WORKER_RECURSION_LIMIT` (40) |
| Shortlist bloat | `qualify_lead` refuses past the limit | `SHORTLIST_SIZE` (10) |
| Hallucinated leads | Qualifying an unknown id returns `ERROR`; prompts require tool-sourced facts | n/a |
| LLM overconfidence | The Qualifier's `fit_score` is **blended** with the heuristic score (60/40) | `scoring.py` |
| Leaking client contact details | `read_lead` shows company and country only, never email or phone | `tools.py` |
| A specialist crashes or stalls | The failure becomes an *observation* for the Head of Sales, and the run continues | n/a |
| The Head of Sales gives up early | **Fallbacks:** heuristic shortlist if empty, table briefing if no report was submitted | `multiagent/runner.py` |

You always get a result. The `trace` shows when a fallback was used (`fallback: …`).

## 5. Code map

```
src/gigscout/multiagent/
├── context.py   RunContext: the shared blackboard (searches, shortlist, briefing, trace)
├── tools.py     The specialists' tools; return text observations, never raise
├── prompts.py   One system prompt per role, each spelling out the ReAct loop and stop condition
├── team.py      create_agent() for each role + the Head of Sales' delegate_to_* tools
└── runner.py    run_team(): kickoff, limits, fallbacks → ScoutResult(mode="team")
```

## 6. Extending the team

**Add a specialist** (e.g. a *Proposal Writer* that drafts a full bid for each top lead):

1. Write its tools in `tools.py` (`build_proposal_tools(ctx)`).
2. Add a system prompt in `prompts.py`.
3. In `team.py`, create it with `create_agent(...)` and add a `delegate_to_proposals` tool.
4. Mention it in the `SUPERVISOR` prompt's team list.
5. Test it with scripted models (see `tests/test_multiagent.py`). No LLM is needed.

**Use different models per role:**
```python
from langchain_ollama import ChatOllama
models = TeamModels(
    supervisor=ChatOllama(model="qwen3:8b"),
    scout=ChatOllama(model="llama3.2:3b"),      # simple tool use, so a small model is fine
    analyst=ChatOllama(model="gemma3:12b"),     # qualification is judgement, so a bigger model helps
    writer=ChatOllama(model="qwen3:8b"),
)
ScoutService(deps, team_models=models).scout(profile, mode="team")
```

## 7. Testing ReAct agents without an LLM

`tests/test_multiagent.py` drives the **real** `create_agent` loops with `ScriptedModel`, a fake
chat model that replays a fixed list of turns (`call("search_source", …)`, then `say("done")`).
This verifies the wiring, tool behaviour, limits and fallbacks deterministically, in milliseconds.
Model *quality* is a separate question; compare live runs in MLflow (`mode` is logged as a param).
