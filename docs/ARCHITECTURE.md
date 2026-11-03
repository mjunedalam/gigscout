# Architecture

## Tech stack (all open source)

| Concern | Choice | Why this one |
|---|---|---|
| Agents (team mode) | **LangChain v1 `create_agent`** | The official ReAct agent loop, built on LangGraph; subagents-as-tools supervisor pattern |
| Orchestration (pipeline mode) | **LangGraph** | Explicit state machine; parallel fan-out (`Send`); bounded loops; first-class MLflow tracing |
| LLM | **Ollama** + `qwen3:8b` (any Ollama model) | Runs locally, free, private (inbound leads never leave your machine); structured output |
| Embeddings | **FastEmbed** + `BAAI/bge-small-en-v1.5` | Top-tier small retrieval model; ONNX on CPU, no PyTorch |
| Vector DB | **ChromaDB** (embedded) | Zero ops: a folder on disk; metadata filters; easy to swap for Qdrant later |
| Experiment tracking and tracing | **MLflow 3** (SQLite backend) | Params, metrics, artifacts and agent traces in one UI |
| HTTP | **httpx** + robots.txt + per-host throttle | Polite, retrying, testable with `respx` |
| Feeds | **feedparser** + BeautifulSoup | Any RSS/Atom board or tender portal; HTML to clean text |
| Interfaces | **Typer** CLI, **FastAPI** REST + webhook | Same service layer behind both |
| Config | **pydantic-settings** | Typed, validated `GIGSCOUT_*` env vars; `SecretStr` for the webhook key |

## Module map

```
src/gigscout/
├── config.py            Settings (env / .env)
├── models.py            Frozen domain models: Lead, Client, AgencyProfile, ScoredLead, ScoutResult
├── http.py              PoliteClient: robots.txt, throttling, retries
├── text.py              HTML→text, whole-word matching
├── scoring.py           Heuristic lead score (fit, budget, opportunity) + LLM blend
├── sources/             Pull: one adapter per source, behind the Source protocol
│   ├── base.py          Protocol: fetch(queries, limit) -> list[Lead]
│   ├── freelancer.py    Freelancer.com official public API → project leads
│   ├── remoteok.py      Remote OK JSON API → hiring signals
│   ├── remotive.py      Remotive JSON API → contract / hiring
│   ├── rss.py           Generic RSS/Atom (We Work Remotely, your RFP feeds)
│   └── registry.py      Which sources are enabled
├── inbound/             Push: channels that send leads to us
│   └── google_ads.py    Lead form webhook payload → inbound Lead
├── store/
│   ├── embeddings.py    Embedder protocol + FastEmbed implementation
│   └── vector_store.py  LeadIndex on ChromaDB (dedupe + semantic search)
├── agent/               Pipeline mode
│   ├── state.py         ScoutState (graph state) + FetchTask
│   ├── prompts.py       Query planning, lead qualification, briefing prompts
│   ├── reasoner.py      Reasoner protocol + Ollama implementation
│   ├── nodes.py         Graph nodes (one method per step) + briefing table
│   └── graph.py         Graph wiring + run_scout()
├── multiagent/          Team mode: Head of Sales + specialist ReAct agents (see MULTI_AGENT.md)
│   ├── context.py       RunContext: the shared blackboard
│   ├── tools.py         Prospector / Qualifier / Outreach Writer tools
│   ├── prompts.py       Per-role system prompts
│   ├── team.py          create_agent() per role + delegate_to_* tools
│   └── runner.py        run_team(): limits + fallbacks
├── rag.py               Question answering over stored leads
├── tracking.py          MLflow run context
├── service.py           Composition root used by CLI and API (scout, search, ask, ingest_inbound)
├── profile_loader.py    YAML agency profile → validated AgencyProfile
├── cli.py               `gigscout …`
└── api.py               FastAPI app + POST /webhooks/google-ads
```

## Key design decisions

1. **One `Lead` model for every channel.** Marketplace projects, contract roles, hiring signals
   and inbound enquiries share one shape, distinguished by `kind`. They live in one memory and are
   ranked in one list, so the sales team sees one priority order.
2. **Pull and push are separate.** Sources implement `fetch()` and the agent decides when to call
   them. Inbound channels can't be searched; they arrive by webhook and go straight into memory.
   Restricting `profile.sources` never hides inbound leads.
3. **Protocols at every external boundary** (`Source`, `Embedder`, `Reasoner`). Tests swap in
   fakes, so the whole system runs in seconds without network or LLM.
4. **The LLM is optional.** With `GIGSCOUT_LLM_PROVIDER=none`, or Ollama unreachable, the agent
   runs on heuristics. Every LLM call is wrapped so that a failure records an error and falls back.
5. **One broken source never sinks a run.** Per-source failures are recorded in `errors`, and the
   run continues with the other sources.
6. **Bounded autonomy.** The broaden loop is capped by `max_iterations`, the team by search budgets
   and recursion limits, and the LLM qualifies only the top `llm_grade_limit` leads.
7. **Immutable data.** All models are frozen Pydantic objects. Nodes return *partial state
   updates*; LangGraph merges them with reducers.
8. **The vector store is the memory.** Chroma IDs (`<source>:<native id>`) are the
   de-duplication ledger, so Google's webhook retries are harmless.
9. **Personal data stays contained.** Inbound email and phone live only in `Lead.client`. They are
   never embedded, never put in prompts (`describe_client` sends company and country only), and the
   LLM runs locally.

## Data flow of one `Lead`

```
source JSON/RSS ──parse()──┐
Google Ads webhook ─to_lead()─┴─► Lead (frozen) ──document()──► embedding ──► Chroma
                                                                  │ metadata: source, kind, posted_ts, payload(JSON)
profile.as_query() ──embed_query()──► nearest neighbours ◄────────┘
     ──► Candidate(similarity) ──heuristic_score()──► ScoredLead ──LLM qualify──► blended ScoredLead (+ pitch)
```

## Scoring formula

```
heuristic   = 0.45 · cosine_similarity + 0.30 · skill_overlap + 0.15 · budget_fit + 0.10 · opportunity
final       = 0.40 · heuristic + 0.60 · llm_score            (top-N only, when an LLM is available)

budget_fit  = min(lead budget in USD / min_budget_usd, 1)    unknown budget → 0.5
opportunity = 1.0 for inbound
              1 / (1 + bid_count / 20) for marketplace leads  (0 bids → 1.0, 20 → 0.5, 60 → 0.25)
              0.5 when competition is unknown
              × 0.5 when the client's country is known and outside target_countries
```
`budget_fit` uses Freelancer's exchange rates to normalise to USD. The weights are constants in
[`scoring.py`](../src/gigscout/scoring.py). Tune them and compare runs in MLflow.

## Extending

- **New source** → see [SOURCES.md](SOURCES.md).
- **Different vector DB** → implement `add_new`, `get`, `search` and `count` like `LeadIndex`.
- **Different LLM** → implement the four `Reasoner` methods (e.g. with `langchain-openai`
  pointed at vLLM or LM Studio).
- **CRM hand-off** (HubSpot, Pipedrive, Slack) → add a step after `report`, or wrap
  `ScoutService.scout` and push `result.matches` above a score threshold.
