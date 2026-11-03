# @gigscout/api

The GigScout backend: lead sources, the multi-agent sales team, vector memory, the REST API, live
events, the run queue and the scheduler. Python 3.12, managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run gigscout create-admin --email you@agency.com     # first user (prompts for a password)
uv run gigscout serve --reload                          # http://127.0.0.1:8000/docs
uv run pytest
```

Run it together with the web app from the repo root with `pnpm dev`. Full documentation lives in
[`../../docs`](../../docs) and the root [README](../../README.md).
