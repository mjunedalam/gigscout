# Lead sources, and the rules of the road

GigScout gets leads in two ways:

- **Pull:** the agent searches sources through **official APIs and public feeds**. It behaves like
  a good guest: it sends an identifying User-Agent, obeys `robots.txt`, makes at most one request
  per second per host, and backs off on 429/5xx errors.
- **Push:** channels such as **Google Ads lead forms** send leads to GigScout's webhook as they
  arrive.

## Built-in sources

| Name | Lead kind | What | Access | Terms to respect |
|---|---|---|---|---|
| `freelancer` | `project` | Freelancer.com active projects: real clients outsourcing work, with budgets and bid counts | Official public API, no key | API terms |
| `remotive` | `contract` / `hiring` | Remotive remote roles; contract roles become `contract` leads | Public JSON API | **Link back and name "Remotive"**; do not republish to other job sites |
| `remoteok` | `hiring` | Remote OK jobs: companies hiring developers | Public JSON API | **Link back to the listing and name "Remote OK"** |
| `weworkremotely` | `hiring` | We Work Remotely programming and DevOps feeds | RSS | Link back |
| `rss` (optional) | configurable, default `project` | Any RSS/Atom feed you add: RFP and tender portals, niche boards | RSS/Atom | Each feed's own terms |
| `google_ads` (optional) | `inbound` | Your own Google Ads lead form submissions | Webhook (push) | Your privacy policy; Google Ads lead form policies |

**Why job boards count as leads.** A company hiring three React developers has budget and a
problem it is trying to solve. Many will consider an agency that can start next week instead of
recruiting for three months. GigScout labels these `hiring` so the Qualifier and the Outreach
Writer pitch *outsourcing or staff augmentation*, not a job application.

**What the public Freelancer API does not show.** Without an authenticated account, the API hides
the client's identity, country and payment-verification status. It does expose `bid_count`, which
GigScout uses as a competition signal: a project with 3 bids is far easier to win than one with 260.

## Fiverr, Upwork and others

| Platform | How it works for an agency | Status in GigScout |
|---|---|---|
| **Fiverr** | Fiverr is a *seller* marketplace: buyers browse gigs that sellers list. Buyer requests ("Briefs") are only shown to sellers inside the Fiverr dashboard. There is no public feed or API of buyer projects, and the Terms of Service forbid scraping. | **Not a pull source.** Win Fiverr work by listing your agency's services as gigs and answering Briefs in Fiverr itself. |
| **Upwork** | The largest source of client projects. It has an official GraphQL API, but it needs an approved developer key and OAuth for your agency account. Public RSS feeds were retired in 2024, and scraping violates the ToS. | **Planned.** Apply for an API key at upwork.com/developer, then add an `UpworkSource` (template below). |
| **LinkedIn, Indeed** | ToS forbid scraping; aggressive anti-bot measures. | Not supported. Use their official partner programs if you qualify. |
| **Google Ads** | Ads don't list projects; they **bring clients to you**. A lead form on your search ads collects the enquiry and Google sends it to a webhook. | **Supported** as the `google_ads` inbound channel. Setup: [OPERATIONS.md](OPERATIONS.md#google-ads-inbound-leads). |

Scraping sites that forbid it gets agency accounts banned, which costs far more than it brings in.
The adapter design makes it easy to add a source *properly* once you have API access.

## Adding a source

### Option A: it has an RSS/Atom feed (no code)

```bash
# .env
GIGSCOUT_RSS_FEEDS=["https://tenders.example.gov/it-services.rss","https://another.dev/feed.xml"]
GIGSCOUT_RSS_FEEDS_KIND=project     # or contract / hiring
```
These appear as the `rss` source and are filtered by the agent's queries.

### Option B: it has a JSON API (about 30 lines)

1. Create `src/gigscout/sources/mysource.py`:

```python
class MySource:
    name = "mysource"

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        leads = []
        for query in queries:
            payload = self._client.get_json(API_URL, params={"q": query, "limit": limit})
            leads.extend(parse(item) for item in payload["items"])
        return leads


def parse(raw: dict) -> Lead:
    return Lead(id=f"mysource:{raw['id']}", source="mysource", title=raw["title"],
                description=html_to_text(raw["body"]), url=raw["url"], kind="project",
                bid_count=raw.get("proposals"), client=Client(country=raw.get("country")))
```

2. Register it in [`sources/registry.py`](../src/gigscout/sources/registry.py).
3. Add a `respx`-mocked test in `tests/test_sources.py` (copy an existing one).

Requests made through `PoliteClient` get robots.txt checks, throttling and retries automatically.

### Option C: it pushes leads to you (a webhook)

Follow [`inbound/google_ads.py`](../src/gigscout/inbound/google_ads.py): a Pydantic model for
the payload, a shared-secret check with `secrets.compare_digest`, a `to_lead()` function, and an
endpoint in `api.py` that calls `ScoutService.ingest_inbound`. Keep contact details (email, phone)
in `Lead.client`, not in the description, so they never get embedded or sent to the LLM.
