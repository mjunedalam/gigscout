# Concepts, Explained with Analogies

GigScout combines a handful of AI ideas. Each is explained below with an everyday analogy, then
with what it actually does in this codebase.

> **The big picture:** GigScout is a **business-development rep for a software agency who never
> sleeps**. Every hour it walks the marketplaces looking for clients who need software built,
> notices companies that are hiring developers (and might rather outsource), picks up the
> enquiries your Google Ads bring in, remembers every lead it has ever seen, compares each one with
> what your agency sells, throws out the scams and the tiny budgets, and leaves a short list on
> your desk: who to contact, why, and what to say first.

---

## 1. AI Agent: the business-development rep

**Analogy.** A chatbot is a *receptionist*: you ask, it answers, it forgets. An **agent** is a
*business-development rep*: you give it a goal ("find us good mobile-app clients this week") and it
decides on its own where to look, what to search for, whether the leads are good enough, and when
to cast a wider net.

**In GigScout.** The agent can *act* (call marketplace APIs and feeds), *remember* (the vector
store), *judge* (LLM qualification) and *decide* (the pipeline loops back when leads are thin; the
team's Head of Sales sends the Prospector out again).

## 2. Leads, and why a job post is one

**Analogy.** A good salesperson reads the business pages, not just the classified ads. "Clinic
chain opens 12 new branches" isn't an order, but it is a reason to call. The same goes here:

| Kind | Salesperson's view |
|---|---|
| `project` | A **classified ad**: "Wanted: booking app, budget $5k." Others are bidding too. |
| `contract` | **"Temp staff wanted"**: they need hands now; the agency can supply a team. |
| `hiring` | A **business-pages signal**: they're hiring three developers. Pitch: "We can start next week." |
| `inbound` | **A customer walked into the shop**: they filled in your ad's form. Hottest lead there is. |

**In GigScout.** Every lead carries a `kind`. Scoring, the Qualifier and the Outreach Writer treat
each kind differently: competition counts against marketplace projects, inbound leads score
highest, and hiring signals get an outsourcing pitch, not a CV.

## 3. LangGraph: the restaurant kitchen ticket rail

**Analogy.** In a busy restaurant, an order ticket moves along a rail between stations: prep →
grill → plating → pass. Every station reads the ticket, adds its part and passes it on. Sometimes
the head chef sends a plate *back* to the grill. Several cooks can work on parts of one order at
the same time.

| Kitchen | LangGraph | GigScout |
|---|---|---|
| Order ticket | **State** | `ScoutState`: agency profile, queries, leads, scores |
| Station | **Node** | `plan_queries`, `fetch_source`, `index`, `retrieve`, `grade`, `report` |
| Rail between stations | **Edge** | `index → retrieve → grade` |
| Head chef sends it back | **Conditional edge** | `should_broaden` → back to `plan_queries` |
| Several cooks at once | **`Send` fan-out** | one `fetch_source` per lead source, in parallel |
| Ticket spike that collects every cook's part | **Reducer** (`operator.add`) | `raw_leads` merges every source's results |

```
START → plan_queries ─┬─► fetch_source (freelancer)     ─┐
                      ├─► fetch_source (remotive)       ─┼─► index → retrieve → grade ─┬─► report → END
                      ├─► fetch_source (remoteok)       ─┤                             │
                      └─► fetch_source (weworkremotely) ─┘                             │
             ▲                                                                          │
             └──────────────── broaden: too few good leads ◄────────────────────────────┘
```

Why not just write a `for` loop? A graph gives you parallel fan-out, bounded retry loops, and
per-node tracing in MLflow for free, and adding a step means adding a node rather than
untangling nested `if`s.

## 4. Webhooks: the shop's letterbox

**Analogy.** Prospecting is walking around town looking for customers. A **webhook** is the
letterbox in your shop door: you don't go anywhere; letters drop in whenever someone sends one. To
make sure nobody slips in junk mail pretending to be from Google, every letter must carry a secret
word you agreed on in advance.

**In GigScout.** Google Ads lead forms post each enquiry to `POST /webhooks/google-ads`. The secret
word is `google_key`, checked with a constant-time comparison. Accepted enquiries become `inbound`
leads in the same memory as everything the agent found itself. See
[OPERATIONS.md](OPERATIONS.md#google-ads-inbound-leads).

## 5. Embeddings: GPS coordinates for meaning

**Analogy.** A GPS turns an address into coordinates, so "nearby" becomes simple arithmetic. An
**embedding model** does the same for text: it turns a sentence into a list of 384 numbers. Texts
with similar *meaning* land at nearby coordinates even when they share no words. "We build patient
portals in React" sits right next to "Clinic needs an online appointment system".

**In GigScout.** [`store/embeddings.py`](../src/gigscout/store/embeddings.py) uses
`BAAI/bge-small-en-v1.5` via FastEmbed. It runs on the CPU, needs no GPU and no PyTorch, and the
model downloads once (~130 MB).

## 6. Vector database: a librarian who shelves by meaning

**Analogy.** A normal database is a library sorted alphabetically. Ask for "car repair" and you
miss the book called *Fixing Automobiles*. A **vector database** is a librarian who shelves books
by *topic*, so asking for "car repair" gets you everything on that shelf, whatever the titles say.

**In GigScout.** [`store/vector_store.py`](../src/gigscout/store/vector_store.py) uses
**ChromaDB**, an embedded database (no server to run) that persists to `data/chroma/`. It does two
jobs:
1. **Memory and de-duplication.** A lead seen yesterday is not re-embedded or re-reported as new,
   and a webhook Google retries is stored only once.
2. **Semantic search.** It finds stored leads closest to *what your agency sells*, filtered by age,
   source and kind.

## 7. RAG (Retrieval-Augmented Generation): the open-book exam

**Analogy.** Asking an LLM about this week's client demand is a *closed-book exam*: it can only
recall what it memorised during training, so it guesses or makes things up. **RAG** makes it an
*open-book exam*. First you **retrieve** the relevant pages (the vector search), then the model
**generates** its answer using only those pages and cites them.

**In GigScout.** RAG shows up in two places:
- **Inside the agent:** the `retrieve` step fetches the most relevant leads, and the `grade` step
  has the LLM qualify each one against your agency profile.
- **`gigscout ask "..."`** ([`rag.py`](../src/gigscout/rag.py)): ask *"Which healthcare leads have
  budgets over $5k?"* and the LLM answers from the retrieved leads with `[n]` citations.

## 8. Lead scoring: a calculator, then a sales manager

**Analogy.** A calculator gives a quick first ranking: does the stack match, is the budget big
enough, how many rivals have already bid? Then an experienced sales manager (the LLM) reads the top
ten in full and spots what arithmetic cannot: "they want a 'quick test task' first: unpaid work",
or "$300 for a marketplace app is not an agency deal". The manager also suggests how to open the
conversation.

**In GigScout.** [`scoring.py`](../src/gigscout/scoring.py) is the calculator and always runs.
[`agent/reasoner.py`](../src/gigscout/agent/reasoner.py) is the sales manager: a local open-source
model via **Ollama** (`qwen3:8b` by default) that returns a structured `LeadAssessment` (score,
reasons, red flags, pitch). The final score blends the two (60% LLM, 40% heuristic). If Ollama is
down, the agent still works on the calculator alone. It degrades; it does not crash.

## 9. MLflow: the flight data recorder

**Analogy.** Every commercial flight carries a *black box* that records altitude, speed and every
cockpit decision. When something goes wrong, or you want the next flight to go better, you replay
it. **MLflow** is the black box for each agent run.

**In GigScout.** [`tracking.py`](../src/gigscout/tracking.py) records, per run:

| What | Examples | Why it matters |
|---|---|---|
| **Params** (the flight plan) | model, agency, stack, lead kinds, minimum budget | Compare runs fairly |
| **Metrics** (the instruments) | `fetched_count`, `new_count`, `inbound_count`, `top_score`, `duration_seconds` | See whether a prompt or model change made results better |
| **Artifacts** (the cargo) | `report.md`, `matches.json`, `run_details.json` | Reopen any past briefing |
| **Traces** (the cockpit voice recorder) | every graph step and every LLM prompt and response | Debug *why* a lead was ranked where it was |

Open the dashboard with `make mlflow-ui`.

---

## 10. ReAct and multi-agent teams: the detective and the sales floor

**ReAct** is a *detective's notebook*: think ("check the butler's alibi"), act (interview the
cook), observe ("he was in the kitchen"), think again, until the case is solved. The model picks
each next step *after* seeing the last result, instead of following a fixed script.

A **multi-agent team** is an agency's *sales floor*. The Head of Sales (Supervisor) assigns work and
checks it, the Prospector (Scout) finds leads, the Qualifier (Analyst) separates real
opportunities from time-wasters, and the Outreach Writer (Writer) drafts what to send. They
coordinate through a shared whiteboard (the blackboard), not by shouting across the room.

Full explanation, guardrails and diagrams: **[MULTI_AGENT.md](MULTI_AGENT.md)**.

---

## How it all fits together: one run, start to finish

*(This walkthrough follows pipeline mode; team mode makes the same moves, but the agents decide
the order and how many times to repeat each one.)*

1. **Plan.** The sales manager turns your agency profile into search phrases (`"mobile app"`, `"saas mvp"`).
2. **Fetch.** Four cooks visit four sources at once, politely: obeying robots.txt, at most one
   request per second per site, and identifying themselves. Meanwhile the letterbox has been
   collecting Google Ads enquiries.
3. **Index.** New leads get GPS coordinates and are shelved by the librarian. Duplicates are ignored.
4. **Retrieve.** The librarian pulls the 25 leads closest to what you sell from the last 14 days.
5. **Grade.** The calculator scores all of them; the sales manager reads the top 10, flags
   time-wasters and writes a pitch line for each.
6. **Decide.** Fewer than 5 good leads? Widen the search and go round again (at most twice).
7. **Report.** A short sales briefing and a ranked table. The black box records everything.
