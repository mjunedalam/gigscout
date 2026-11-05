# Operations

## Running on a schedule

**Simple:** `uv run gigscout watch -p profiles/example.yaml --every 60` (minimum 5 minutes).

**Robust (macOS/Linux cron):** run once an hour and keep a log:
```cron
0 * * * * cd /path/to/gigscout && /path/to/uv run gigscout scout -p profiles/example.yaml >> data/scout.log 2>&1
```

Re-runs are cheap: leads already in ChromaDB are not re-embedded, and the briefing ranks
everything from the last `MAX_LEAD_AGE_DAYS`, inbound leads included.

## Pitches: the agents write, a person approves

Open **Pitches** in the web app. In the Autopilot panel an owner or admin sets:

| Setting | What it does |
|---|---|
| Draft pitches after every run | At the end of each run the agents write a pitch for its best leads: new (nobody working them), not flagged as a scam or duplicate, and not pitched before. |
| Only leads scoring at least | The score floor (default 70). |
| At most, per run | A cap, so the queue stays reviewable (default 5). |
| Follow up after N days | Once a day (09:00) a follow-up is drafted for each email with no reply after N days. One per email. 0 turns it off. |
| Only owners and admins approve | Members can still edit drafts, but only owners and admins can send or reject them. |

**Nothing is sent automatically.** Every draft waits in *Waiting for approval* until a person:

- **Approves and sends an email.** This needs SMTP set up. At most 30 emails an hour per person.
- **Approves a marketplace bid as posted** after copying it into the listing. Marketplaces forbid automated bidding, so a person always posts the bid.
- **Rejects it** with a reason. Rejected pitches stay visible in the *Rejected* tab.

Approving moves the lead to *contacted*. Every approval and rejection is recorded in the audit log, along with each draft the agents write.

## Pipeline and owner report

**Pipeline** shows every step a lead takes, from *Found* to *Won* (or *Lost*), for 7, 30 or 90 days, or a
year. Each step shows four numbers:

- how many leads reached it;
- the change from the period before;
- the share of leads from the step before that got there;
- the median time it took.

It also flags leads that have waited too long: pitches not approved within 2 days, emails with no answer
after 7 days, and proposals open longer than 14 days. Click a step to see its leads.

**Reports** is the owner view for the same period:

- revenue won;
- reply and approval rates;
- sources ranked by the value they won;
- what each person and the agents did.

Use **CSV** to get a spreadsheet, and **Print / PDF** to save a clean copy. To count a won deal as revenue,
set its value on the lead (in Proposal or Won).

The history starts from your existing data the first time this version runs.

## Knowledge base: pitches built on your real work

Add your case studies, past proposals, portfolio and rates under **Knowledge base**. You can paste text or
upload a PDF, `.txt` or `.md` file of up to 10 MB. PDFs need real text: a scanned PDF needs OCR first.

Once the knowledge base has documents:

- The pitch writer gets the passages that best match the lead. It may mention only the past work, clients,
  numbers and prices found in them.
- Every sentence in a pitch that claims something about your company is checked against your documents.
  Claims they don't back show in orange before you approve. They are checked again after every edit, and you
  can click **Check again** at any time.
- **Try it** shows what the agents would cite for a lead you describe.

## Replies: the agents read them, a person answers

Client replies land in **Inbox**. For each reply the agents:

1. **Read what it means:** wants a call, interested, a question, not now, not interested, an auto-reply, or
   unsubscribe.
2. **Move the lead:**
   - Every real reply records the *Replied* step.
   - *Wants a call* moves the lead to **proposal**.
   - *Not interested* and *unsubscribe* mark it **lost**.
3. **Draft an answer** in your voice, from your knowledge base. Nothing is drafted for no, an auto-reply or
   unsubscribe. The answer waits in Inbox and Pitches like any other pitch: nothing goes out until a person
   approves it. Approving an email answer sends it in the client's thread, and the reply is marked handled.

**Reading replies from your mailbox (optional).** Set the same mailbox the emails are sent from in
`apps/api/.env`:

| Setting | Example |
|---|---|
| `GIGSCOUT_IMAP_HOST` | `imap.gmail.com` |
| `GIGSCOUT_IMAP_USER` | `sales@your-agency.com` |
| `GIGSCOUT_IMAP_PASSWORD` | an app password, never your main password |
| `GIGSCOUT_IMAP_FOLDER` | `INBOX` (default) |
| `GIGSCOUT_IMAP_POLL_MINUTES` | `10` (default) |
| `GIGSCOUT_IMAP_AUTHSERV_ID` | `mx.google.com` for Gmail. It's the name your mail server writes first in each email's `Authentication-Results` header. |

Mail is read without marking it as read. Only emails that answer something GigScout sent are used. The rest of
the mailbox is ignored. Replies are matched in two ways:

- **By their thread headers.** GigScout's message ids are unique, so this always finds the one right message.
- **By the sender's address, within 45 days.** This is used only when your mail server confirmed the sender
  and exactly one workspace wrote to that address.

A reply moves a lead only when both of these are true:

- **Your own mail server confirmed the sender.** The server named in `GIGSCOUT_IMAP_AUTHSERV_ID` recorded a
  DMARC pass for the sender's domain, or a DKIM pass signed by it. A result written by anyone else is
  ignored, and so is any "pass" that appears only inside a comment.
- **The sender is the person or company you wrote to.**

Anything else is still shown and answered as a draft, but marked **unverified sender**. It doesn't change the
lead or the pipeline, and its answer goes only to the address you originally wrote to. Until
`GIGSCOUT_IMAP_AUTHSERV_ID` is set, every reply is treated this way.

Without a mailbox, or for marketplace messages, open the lead and use **Log a reply** on the sent message.

## Google Ads inbound leads

When a prospect fills in the lead form on one of your Google Ads, Google sends the submission to
GigScout as JSON. GigScout checks the shared key, stores the enquiry as an `inbound` lead, and the
next `scout` run ranks it with everything else (inbound leads get the top opportunity score).

1. **Pick a key.** Generate a long random value, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`,
   and set it in `.env`:
   ```bash
   GIGSCOUT_GOOGLE_ADS_WEBHOOK_KEY=<that value>
   ```
2. **Expose the API over HTTPS.** Google only calls public HTTPS URLs. Run `gigscout serve --host 0.0.0.0`
   behind a reverse proxy with TLS (Caddy, nginx, a cloud load balancer), or use a tunnel such as
   Cloudflare Tunnel for a trial. The webhook URL is `https://<your-host>/webhooks/google-ads`.
3. **Connect the form.** In Google Ads, open the lead form asset → *Lead delivery* → *Webhook
   integration*. Paste the URL and the same key.
4. **Test it.** Click *Send test data*. GigScout answers `{"status": "test_received"}` and stores
   nothing. Real submissions answer `stored`, or `duplicate` if Google retries.
5. **Ask useful questions.** Add custom questions such as *"What do you need built?"* and
   *"Project budget"*. Answers become the lead's description, and a question containing "budget"
   is parsed into the lead's budget.

| Response | Meaning |
|---|---|
| `200 {"status":"stored"}` | New inbound lead saved |
| `200 {"status":"duplicate"}` | Already had this `lead_id` (Google retried) |
| `200 {"status":"test_received"}` | Google's test button; nothing saved |
| `401` | Wrong `google_key`; check that both sides have the same key |
| `404` | `GIGSCOUT_GOOGLE_ADS_WEBHOOK_KEY` is not set, so the webhook is off |
| `422` | Payload missing `lead_id` or `google_key` |

**Production hardening** (not built in): put the API behind the reverse proxy's rate limiting,
don't expose `/scout`, `/search` and `/ask` publicly (they are unauthenticated; expose only
`/webhooks/google-ads` or add auth at the proxy), and back up `data/`.

## MLflow

```bash
make mlflow-ui      # http://127.0.0.1:5000
```
- **Experiments → gigscout → a run** shows params (agency, stack, lead kinds, minimum budget),
  metrics (`fetched_count`, `new_count`, `inbound_count`, `top_score`) and the `report.md` /
  `matches.json` artifacts.
- **Traces tab** shows the agent run step by step, including every LLM prompt and response.
  Use it to see why a lead scored the way it did.
- To compare two models, run once with `GIGSCOUT_LLM_MODEL=qwen3:8b` and once with
  `gemma3:12b`, then select both runs and click **Compare** on `top_score`, `mean_top5_score` and
  `duration_seconds`.

## Data locations

| Path | Contents | Safe to delete? |
|---|---|---|
| `data/chroma/` | Vector store: every collected lead, **including inbound contact details** | Pulled leads are re-fetched by the next run; **inbound leads are lost for good** |
| `data/mlflow.db`, `mlruns/` | MLflow runs and artifacts (briefings may name inbound clients) | Yes; you lose history |

Treat `data/` as customer data: keep it out of git (it is in `.gitignore`), off shared drives, and
delete inbound leads you no longer need.

**Upgrading from 0.1.** Leads now live in a new collection (`leads`), so data collected by 0.1
(the `projects` collection) is ignored. The first 0.2 run re-collects pulled leads.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Ollama not reachable … running without an LLM` | Start Ollama (`ollama serve`) or set `GIGSCOUT_LLM_PROVIDER=none` |
| A `warning: <source>: …` line | That source failed (timeout, rate limit, API change). The rest of the run still completes. If it persists, the API changed: update its `parse()` |
| `robots.txt disallows …` | The site asked crawlers not to fetch that URL. Respect it and remove the feed |
| Run is slow | LLM qualification dominates. Lower `GIGSCOUT_LLM_GRADE_LIMIT`, use a smaller model (`llama3.2:3b`), or set `MAX_ITERATIONS=1` |
| Too many tiny or irrelevant leads | Raise `min_budget_usd`, add `keywords`/`services`, extend `exclude`, or drop `hiring` from `kinds` |
| Inbound lead doesn't show in the briefing | Check `kinds` includes `inbound` and the lead is newer than `MAX_LEAD_AGE_DAYS` |
| First run hangs at "Scouting…" | It is downloading the embedding model (~130 MB) once |
