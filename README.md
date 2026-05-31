# PyNote

A NotebookLM-style RAG application: upload sources, ask grounded questions, get inline citations that jump to the cited source span.

- **Roadmap** → [PLAN.md](PLAN.md)
- **Cost & provider choices** (free-tier first) → [COSTS.md](COSTS.md)

## Status

🚧 **M0 — Foundation.** Multi-tenant API + worker + web skeleton, Clerk auth (or dev-headers fallback), Postgres+pgvector, Redis, MinIO, Alembic migrations, LangSmith tracing. Smoke test against Claude via GitHub Models.

Next: [M1 — Single-PDF ingestion](PLAN.md#m1--single-pdf-ingestion-no-chunking-yet--m).

## Architecture (M0)

```
apps/web (Next.js 15 + Clerk)
        │  fetch /api/v1/* (proxied)
        ▼
apps/api (FastAPI)            ← Clerk JWT or dev-headers
        │  SQLAlchemy + arq enqueue
        ▼
Postgres 16 + pgvector + pg_trgm    Redis (arq queue)    MinIO (R2-compatible)
        ▲
        │  SQLAlchemy
apps/worker (arq)             ← LangChain → ChatAnthropic (GH Models) | Gemini
```

## Quickstart

### Prerequisites
- Python ≥ 3.12
- Node ≥ 22 + pnpm 9
- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) for Python deps
- **Recommended**: [just](https://github.com/casey/just) (`winget install Casey.Just`) + [mprocs](https://github.com/pvolok/mprocs) (`scoop install mprocs`) — one-word commands instead of 5-line incantations.

### TL;DR

Works the same in **Git Bash**, **WSL**, **PowerShell**, **Linux**, **macOS** — the Justfile uses `bash` for all recipes.

```bash
just env       # copy .env templates
just setup     # install all deps
just up        # start postgres + redis + minio
just migrate   # apply DB migrations
just dev       # api + worker + web in one terminal (needs mprocs)
just test      # run the test suite
just check     # full lint + typecheck + test (what CI runs)
just doctor    # print installed tool versions
```
`just` with no args lists every available command.

**Prefer Make?** A [Makefile](Makefile) mirrors every recipe — use `make help` for the list. Works in Git Bash, WSL, Linux, macOS (`make` is bundled with Git for Windows).

### 1. Install deps
```powershell
# Python workspace
uv sync
uv pip install -e packages/core -e apps/api -e apps/worker

# Web
cd apps/web; pnpm install; cd ../..
```

### 2. Configure environment
```powershell
Copy-Item .env.example .env
Copy-Item apps/web/.env.example apps/web/.env.local
```
Then edit both `.env` files. Minimum keys for M0:
- `ANTHROPIC_API_KEY` — a GitHub PAT (no scopes needed) for free Claude via GitHub Models. Get one at https://github.com/settings/tokens.
- `LANGSMITH_API_KEY` — optional, for tracing. Free hobby tier at https://smith.langchain.com.
- Clerk keys are **optional in dev**: if you leave `CLERK_JWKS_URL` empty, the API trusts `X-Dev-User` / `X-Dev-Org` headers, so you can test without setting up Clerk.

### 3. Start local services
```powershell
docker compose -f docker-compose.dev.yml up -d
```
Brings up Postgres (5432), Redis (6379), MinIO (9000, console at 9001).

### 4. Run migrations
```powershell
uv run alembic upgrade head
```

### 5. Run api + worker + web

Easiest — one terminal with `just dev` (needs `mprocs`), or `just up && just api` / `just worker` / `just web` in three terminals.

Raw commands if you don't want the runner:
```bash
# Terminal 1 — API
#   Do NOT use `uvicorn pynote_api.main:app` directly on Windows: psycopg3 async
#   requires WindowsSelectorEventLoopPolicy, which must be installed BEFORE
#   uvicorn loads. The module entrypoint sets it first.
uv run python -m pynote_api

# Terminal 2 — Worker
uv run arq pynote_worker.main.WorkerSettings

# Terminal 3 — Web
cd apps/web && pnpm dev
```

Visit http://localhost:3000.

### 6. Smoke test
```powershell
# Unit tests (no live services needed beyond Postgres for some).
uv run pytest -q

# End-to-end LLM ping (requires ANTHROPIC_API_KEY set).
uv run pytest packages/core/tests/test_llm_factory.py::test_smoke_chat_ping -q
```

A successful smoke test produces one trace in your LangSmith project (`pynote-dev` by default).

### 7. Quick API check without the web app
```powershell
# Create a notebook using dev-header auth (works when CLERK_JWKS_URL is unset).
curl -X POST http://localhost:8000/api/v1/notebooks `
  -H "Content-Type: application/json" `
  -H "X-Dev-User: dev_user_1" `
  -H "X-Dev-Org: dev_org_1" `
  -d '{"title":"My first notebook"}'
```

## Repository layout

```
apps/
  api/          FastAPI service — routes, auth, deps
  worker/       arq worker — ingest, embedding, outline jobs (M1+)
  web/          Next.js 15 + Clerk + Tailwind
packages/
  core/         Shared Python: settings, models, db, llm, tracing
  shared-types/ OpenAPI → TypeScript (populated in M1)
infra/
  postgres-init.sql
alembic/        Migrations
eval/           Golden set + Ragas harness (populated in M3/M7)
PLAN.md         Roadmap (M0 → M17)
COSTS.md        Provider matrix + free-tier defaults
```

## M0 acceptance criteria

- [x] `docker compose up` brings up a working stack
- [ ] After alembic upgrade, the dashboard lists notebooks for a Clerk org
- [ ] `noop_task` enqueued via API completes in the worker
- [ ] One LangSmith trace visible from `test_smoke_chat_ping`

(The last three depend on real environment values being filled in; the scaffolding is in place.)

## License

MIT.
