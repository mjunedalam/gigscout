# Deploying GigScout

One server runs everything with Docker Compose: Postgres, the API, the web app behind Caddy (automatic HTTPS and
security headers), nightly backups, and optionally Ollama for the AI agents.

## What you need

- A Linux server with Docker (2 CPU / 4 GB RAM is enough without a local LLM; 16 GB+ to run Ollama on it).
- A domain, e.g. `leads.youragency.com`, with an A record pointing at the server, and ports 80 and 443 open.

## First start

```bash
git clone <your repo> gigscout && cd gigscout
cp deploy/.env.example .env              # POSTGRES_PASSWORD (long random) and GIGSCOUT_SITE_ADDRESS (your domain)
cp apps/api/.env.example apps/api/.env   # GIGSCOUT_ADMIN_EMAIL / GIGSCOUT_ADMIN_PASSWORD, SMTP, CRM, ...
docker compose up -d --build
```

Open `https://<your domain>` and sign in with the admin account. Caddy gets the certificate on first request.
Both `.env` files are gitignored: never commit them.

**The AI agents** need an Ollama endpoint. Either run it here (`docker compose --profile llm up -d`, then
`docker compose exec ollama ollama pull qwen3:8b`), or point `GIGSCOUT_OLLAMA_BASE_URL` in `.env` at another
machine. Without one, runs use the fast pipeline and heuristic scoring.

**Or use Claude** instead of a local model: set `GIGSCOUT_LLM_PROVIDER=anthropic` and `GIGSCOUT_ANTHROPIC_API_KEY`
in `apps/api/.env` (optionally `GIGSCOUT_ANTHROPIC_MODEL`, default `claude-sonnet-5-5`). No GPU needed; lead text
and company profiles are sent to Anthropic's API, contact details never are.

## What is where

| Service | Data | Notes |
|---|---|---|
| `db` | volume `pgdata` | Postgres 16; not published outside the compose network |
| `api` | volume `apidata` (`/data`) | lead vector store, embedding model cache; trusts Caddy's `X-Forwarded-For` so rate limits see visitors |
| `web` | volumes `caddy_data`, `caddy_config` | the only published service (80 → 443); HSTS, CSP, no framing |
| `backup` | `./backups` | daily at `BACKUP_HOUR_UTC` (default 02:00), keeps `BACKUP_KEEP_DAYS` (default 14) |

Session cookies are `Secure`, `HttpOnly` and `SameSite=Strict`. MLflow tracking is off in the container.

## Backups and restore

Each night the `backup` service writes `db-<time>.dump` (pg_dump) and `appdata-<time>.tar.gz` (the vector store)
to `./backups`. Copy that folder off the server too (e.g. `rclone` to object storage). Back up now with
`docker compose exec backup sh /backup.sh`.

Restore:

```bash
docker compose stop api
docker compose exec -T db sh -c 'dropdb -U gigscout gigscout && createdb -U gigscout gigscout'
docker compose exec -T db pg_restore -U gigscout -d gigscout --no-owner < backups/db-<time>.dump
docker compose run --rm -v "$PWD/backups:/backups" --entrypoint sh api \
  -c 'rm -rf /data/chroma && tar -xzf /backups/appdata-<time>.tar.gz -C /data'
docker compose start api
```

## Upgrading

```bash
git pull && docker compose up -d --build
```

The API upgrades the database schema itself at startup (new tables and columns; existing rows are kept). Take a
backup first.

## Moving from the development SQLite database

The development app keeps its data in `apps/api/data/gigscout.db` and `apps/api/data/chroma/`. To start production
with it, copy `chroma/` into the `apidata` volume and move the SQLite rows into Postgres with a tool such as
`pgloader`; or start fresh and let the agents fill the new database.

## CI

`.github/workflows/ci.yml` runs on every push and pull request: lint, type checks, all tests and the web build;
the API tests again on a real Postgres; and both Docker image builds.
