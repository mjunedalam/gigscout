# GigScout 🔎

**An AI lead scout for software development companies. It searches freelance marketplaces and job
boards, catches inbound enquiries from your Google Ads, qualifies every lead against what your agency
sells, and hands your sales team a ranked briefing with a ready-to-use opening line for each.**

> Think of it as a **business-development rep who never sleeps**. Every hour it walks the
> marketplaces looking for clients who need software built, notices companies that are hiring
> developers (and might rather outsource), picks up the enquiries your ads bring in, throws out the
> scams and the tiny budgets, and leaves a short list on your desk: *who to contact, why, and what
> to say first*. New to agents, RAG or vector databases? Start with
> **[docs/CONCEPTS.md](docs/CONCEPTS.md)**, which explains every idea with an everyday analogy.

```
 PULL (the agent goes looking)                     PUSH (clients come to you)
 Freelancer.com · Remotive · Remote OK ·           Google Ads lead forms
 We Work Remotely · your RSS/RFP feeds             └─► POST /webhooks/google-ads
          │                                                   │
          ▼                                                   ▼
   ┌─────────────────── shared lead memory (ChromaDB) ──────────────────┐
   └──────────────────────────────────┬──────────────────────────────────┘
                                      ▼
        Head of Sales (ReAct supervisor) ─► Prospector · Qualifier · Outreach Writer
                                      ▼
            Sales briefing: ranked leads, red flags, a pitch line for each
```

## What counts as a lead

| Kind | What it means for an agency | Where it comes from |
|---|---|---|
| `project` | A client wants a project built and is taking proposals | Freelancer.com, your RFP/tender RSS feeds |
| `contract` | A company wants contractors: staff augmentation work | Remotive (contract roles) |
| `hiring` | A company is hiring developers in-house: a *buying signal*, so pitch outsourcing instead | Remote OK, Remotive, We Work Remotely |
| `inbound` | A prospect filled in your Google Ads lead form | Google Ads webhook |

## Features

- **Multi-agent ReAct sales team (LangChain `create_agent` on LangGraph):** a Head of Sales
  delegates to a Prospector, a Qualifier and an Outreach Writer, each running its own
  Reason → Act → Observe loop with guardrails and fallbacks. See
  **[docs/MULTI_AGENT.md](docs/MULTI_AGENT.md)**.
- **Lead qualification built for agencies:** stack and service fit, deal size against your minimum,
  **competition** (how many bids a project already has), target countries, and red flags (unpaid
  tests, off-platform payment, budgets too small for a team).
- **A pitch line for every qualified lead**, plus short outreach messages for the top three.
- **Inbound leads from Google Ads:** a signed webhook turns lead form submissions into leads,
  ranked in the same list as everything else.
- **Deterministic pipeline mode (LangGraph):** sources are fetched in parallel, and the search
  broadens on its own when results are thin. It works with no LLM at all.
- **Vector memory (ChromaDB + bge embeddings):** every lead is de-duplicated and searchable by meaning.
- **RAG questions over your pipeline:** `gigscout ask "Which fintech leads have budgets over $5k?"`.
- **MLflow tracking:** params, metrics, briefings and full agent traces for every run.
- **Plays by the rules:** official APIs, feeds and webhooks only; no scraping of sites that forbid
  it ([why](docs/SOURCES.md)).
- **CLI + REST API + VS Code debug configs**, typed config, 66 tests with 96% coverage.

## Quick start

**Requirements:** Python 3.12, [uv](https://docs.astral.sh/uv/), and optionally
[Ollama](https://ollama.com) for LLM features.

```bash
cd gigscout
uv sync                                   # install
ollama pull qwen3:8b                      # optional: the local LLM
cp .env.example .env                      # optional: tweak settings
# edit profiles/example.yaml to describe YOUR agency

uv run gigscout scout -p profiles/example.yaml     # run the agent once
```

The first run downloads the embedding model (~130 MB). A full run with LLM qualification takes a
few minutes on a laptop; set `GIGSCOUT_LLM_PROVIDER=none` for a run in seconds.

## Commands

| Command | What it does |
|---|---|
| `gigscout scout -p profile.yaml` | Run once: team mode if an LLM is up, else pipeline |
| `gigscout scout --mode team --trace` | Multi-agent ReAct run, printing who did what |
| `gigscout scout --mode pipeline` | Fixed graph, works without an LLM |
| `gigscout watch -p profile.yaml --every 60` | Re-run every 60 minutes; only new leads are added |
| `gigscout search "react native booking app"` | Semantic search over every lead collected |
| `gigscout ask "best fintech leads this week?"` | RAG: LLM answer with `[n]` citations |
| `gigscout sources` | List pull sources and enabled inbound channels |
| `gigscout serve` | REST API at http://127.0.0.1:8000/docs (and the Google Ads webhook) |
| `make mlflow-ui` | MLflow dashboard at http://127.0.0.1:5000 |

Add `-v` for verbose logs: `gigscout -v scout`.

### REST API

```bash
curl -X POST localhost:8000/scout -H 'content-type: application/json' \
     -d '{"name":"Acme Studio","skills":["python","react"],"services":["web app development"],"min_budget_usd":2000}'
curl 'localhost:8000/search?q=mobile%20app&k=5'
curl -X POST localhost:8000/ask -H 'content-type: application/json' -d '{"question":"any healthcare leads?"}'
```

`POST /webhooks/google-ads` receives Google Ads lead forms; set it up with
[docs/OPERATIONS.md](docs/OPERATIONS.md#google-ads-inbound-leads).

## Your agency profile

```yaml
name: Acme Software Studio
pitch: A 12-person studio building custom web platforms, mobile apps and AI integrations.
services: [web application development, mobile app development, ai chatbot integration]
skills: [python, django, react, react native, aws]       # required: your delivery stack
keywords: [web app, mobile app, saas mvp]                # seeds the search queries
industries: [fintech, healthcare]
exclude: [wordpress, unpaid, "data entry"]               # hard filter
min_budget_usd: 1500                                     # smallest deal worth your time (scored, not filtered)
target_countries: [United States, United Kingdom]        # clients elsewhere score lower; empty = any
kinds: [project, contract, hiring, inbound]
# sources: [freelancer, remotive]                        # default: all (inbound is always included)
```

## Configuration

Every field in [`config.py`](src/gigscout/config.py) can be set as an environment variable with
the `GIGSCOUT_` prefix (see [`.env.example`](.env.example)). The most useful ones:

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `none` = heuristics only |
| `LLM_MODEL` | `qwen3:8b` | Any Ollama model with tool/JSON support |
| `LLM_GRADE_LIMIT` | `10` | How many top leads the LLM qualifies |
| `MAX_LEAD_AGE_DAYS` | `14` | Ignore older leads |
| `MIN_GOOD_MATCHES` / `GOOD_MATCH_THRESHOLD` | `5` / `0.6` | When to broaden the search |
| `RSS_FEEDS` / `RSS_FEEDS_KIND` | `[]` / `project` | Extra feeds (e.g. RFP/tender portals) and the lead kind they carry |
| `GOOGLE_ADS_WEBHOOK_KEY` | unset | Shared secret for the Google Ads webhook; unset = disabled |

## Development

```bash
make test        # pytest + coverage (no network, no LLM; every external boundary is faked)
make lint        # ruff
```

## Documentation

| Doc | For |
|---|---|
| [docs/CONCEPTS.md](docs/CONCEPTS.md) | Agents, LangGraph, embeddings, vector DB, RAG and MLflow, explained with analogies |
| [docs/MULTI_AGENT.md](docs/MULTI_AGENT.md) | The ReAct pattern and the sales team of agents, with guardrails and how to extend it |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Stack choices, module map, design decisions, scoring formula |
| [docs/SOURCES.md](docs/SOURCES.md) | Every lead source, its terms, why Fiverr and Upwork work differently, adding a source |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Scheduling, Google Ads webhook setup, MLflow, troubleshooting |

## Responsible use

Briefings always link back to the original listing and name the source, as the providers' API
terms require. Use leads to send relevant, individual proposals, not bulk outreach. Don't
republish listings or raise request rates. Inbound leads contain personal data (name, email,
phone): keep `data/` private and follow the privacy rules that apply to you (e.g. GDPR). See
[docs/SOURCES.md](docs/SOURCES.md).
