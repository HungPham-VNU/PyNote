# PyNote

A NotebookLM-style RAG application: upload PDFs, ask grounded questions, click any citation to jump to the exact source span. Built with Postgres + pgvector, LangGraph, and Anthropic's Citations API.

- **Roadmap** → [PLAN.md](PLAN.md)
- **Costs & provider choices** → [COSTS.md](COSTS.md)
- **Ship runbook** → [SHIP.md](SHIP.md)

## Status

✅ **v1 shipped** — M0 through M7 plus the post-v1 notebook summary artifact and the Material-3 dark theme.

| What it does | How |
|---|---|
| Multi-tenant cloud-deployable web app | Clerk org-scoped auth + Postgres RLS-ready schema |
| PDF upload → parse → chunk → embed → outline | PyMuPDF (font-based heading detection) + structure-aware chunker (paragraph/sentence/section boundaries) + fastembed BGE-small (384-dim) |
| Hybrid retrieval | pgvector dense + tsvector sparse, RRF fused in a single SQL CTE |
| Optional rerank | Voyage rerank-2.5 (200M tok/mo free) |
| Streaming chat with citations | LangGraph `retrieve → generate → map_citations` with AsyncPostgresSaver, SSE token stream |
| Citation roundtrip validator | Char-offset slices from chunks compared against Anthropic `cited_text` |
| PDF viewer with span highlight | `react-pdf` slide-over + CSS Custom Highlight API |
| Suggested-question chips | Gemini Flash / Haiku outline at ingest time |
| Notebook summary artifact | One structured Opus/Gemini Pro call, persisted on `notebook.settings` |
| Eval harness with ship gate | Citation-grounding + lite Ragas-style metrics + optional real Ragas |

## Architecture

```
apps/web (Next.js 15 + Clerk + react-pdf + dark Material-3 theme)
        │  SSE / fetch /api/v1/*
        ▼
apps/api (FastAPI)         ← Clerk JWT (or X-Dev-* in dev)
        │
        ├── notebooks, sources/upload, /file, chat (SSE), threads/{id}/history,
        │   search (hybrid RRF), summary (Option A)
        │
        ▼  enqueue arq  ─────────────────────────────────┐
apps/worker (arq)                                        │
  parse_source → embed_source → outline_source           │
                                                         │
LangGraph chat_graph (AsyncPostgresSaver)                │
  retrieve → generate (Anthropic Citations API) →        │
  map_citations (char-offset roundtrip)                  │
                                                         ▼
Postgres 16 + pgvector + pg_trgm   Redis (arq queue)   MinIO / R2
```

## Quickstart

### Prerequisites
- Python ≥ 3.12
- Node ≥ 22 + pnpm
- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) for Python deps
- **Recommended**: [just](https://github.com/casey/just) + [mprocs](https://github.com/pvolok/mprocs)

### TL;DR

```bash
just env       # copy .env templates
just setup     # install all deps
just up        # postgres + redis + minio
just migrate   # apply all migrations (extensions + tables + indexes)
just dev       # api + worker + web in one terminal (needs mprocs)
just test      # run the test suite — 60 passed, 2 skipped
```

`just doctor` prints every required tool's version. A [Makefile](Makefile) mirrors every recipe.

### 1. Install deps
```bash
uv sync
uv pip install -e packages/core -e apps/api -e apps/worker
cd apps/web && pnpm install && cd ../..
```

### 2. Configure environment
```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
```

The keys that **actually work** for v1 (see "Provider gotchas" below for the failure modes):

| Var | Where | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → API Keys → Create | `sk-ant-…`. New accounts get $5 free credit — covers a demo easily. |
| `GOOGLE_API_KEY` | https://aistudio.google.com/apikey | Free tier. Used for outline (Flash, 1500/day) and summary on free-tier mode. |
| `EMBEDDING_DIM` | `.env` | Must be **384** to match the default `BAAI/bge-small-en-v1.5`. The migration reads this at runtime. |
| `PROVIDER_TIER` | `.env` | `prod` to route summary/outline through Claude when you have the Anthropic key. `free` to route them through Gemini. |
| `CLERK_*` | https://dashboard.clerk.com | Required for the web app. Enable Organizations + disable Personal accounts so the JWT carries `org_id`. |
| `LANGSMITH_API_KEY` | https://smith.langchain.com | Optional — auto-traces every LangGraph node. |
| `VOYAGE_API_KEY` | https://voyageai.com | Optional — rerank-2.5 has 200M tok/mo free. Falls back to top-K hybrid without it. |

**Do not set `ANTHROPIC_BASE_URL`.** Leave it unset (or `https://api.anthropic.com`). The previously documented GitHub Models route does not work with `langchain-anthropic` — see "Provider gotchas" below.

### 3. Start local services
```bash
just up
```

### 4. Run migrations
```bash
just migrate
```

Creates extensions (`vector`, `pg_trgm`, `btree_gin`), tenancy tables, source/chunk schema, HNSW + GIN indexes, and the LangGraph checkpoint tables (auto-created on first API startup).

### 5. Run api + worker + web
One terminal with mprocs, or three terminals:

```bash
# Windows-safe API entrypoint (sets WindowsSelectorEventLoopPolicy before uvicorn)
uv run python -m pynote_api
# NEVER use `uvicorn pynote_api.main:app` directly on Windows — psycopg3 async dies on ProactorEventLoop.

uv run python -m pynote_worker     # same Windows fix for arq
cd apps/web && pnpm dev
```

Visit http://localhost:3000.

### 6. Smoke tests
```bash
uv run pytest -q                                  # 60 passed, 2 skipped
uv run python -m eval.prototype.m3 health         # checks providers + DB + chunk count
```

## Repository layout

```
apps/
  api/      FastAPI service — routes (notebooks, sources, search, chat, summary, jobs, health), auth
  worker/   arq worker — parse_source, embed_source, outline_source
  web/      Next.js 15 + Clerk + react-pdf + Material-3 dark theme
packages/
  core/     Shared Python — settings, models, db, llm factory, embeddings, chunker,
            retrieval (hybrid SQL + Voyage rerank), citations (parse + validate),
            chat_graph (LangGraph), outliner, summarizer, tracing
infra/      Postgres init + docker-compose service config
alembic/    Migrations 0001 (tenancy) → 0002 (sources) → 0003 (chunks + HNSW + GIN)
eval/
  prototype/  M3 CLI: health / ask / chat / select / stability / bulk
  metrics.py  Citation grounding + lite faithfulness/relevancy + ship-gate aggregator
  ragas_metrics.py  Optional Ragas integration (cheap-model judge)
  run.py    M7 ship-gate runner — exit code === gate verdict
  golden/   Sample JSONL question sets
PLAN.md     Roadmap M0 → M17
COSTS.md    Provider matrix (with the gotchas listed below)
SHIP.md     Demo runbook + gate thresholds
```

## v1 acceptance — what works

- [x] PDF upload → status pill flips `parsing → embedding → ready` within ~30 s
- [x] "Try asking…" chips render once the outline job finishes
- [x] Chat tokens stream via SSE
- [x] Citation pills `[1] [2]` appear after the answer; click → PDF drawer at the cited page with yellow highlight
- [x] Conversation persists across page refresh (`?thread=` URL + `PostgresSaver`)
- [x] Notebook summary generates in ~10 s and caches on `notebook.settings`
- [x] Eval gate: `python -m eval.run --notebook <uuid> --file eval/golden/sample.jsonl` exits 0 when `citation_grounding ≥ 0.90`

## Provider gotchas (learned the hard way)

| Symptom | Real cause | Fix |
|---|---|---|
| Chat returns `401 - No authorization header` | `ANTHROPIC_BASE_URL` points at GitHub Models. The Anthropic SDK sends `x-api-key`; GH Models wants `Authorization: Bearer`. **The GH Models bridge in COSTS.md is broken.** | Unset `ANTHROPIC_BASE_URL` and use a real `sk-ant-…` key. $5 signup credit covers a demo. |
| Summary returns 400 `temperature is deprecated for this model` | Opus 4+ rejects the `temperature` parameter. | Already fixed in `_anthropic_kwargs` — temperature is no longer set for any Anthropic call. |
| Summary returns 429 RESOURCE_EXHAUSTED | Gemini 2.5 Pro free tier is 50 req/day. | Either set `PROVIDER_TIER=prod` to use Opus, or set `GEMINI_MODEL_HEAVY=gemini-2.0-flash` (1500/day). |
| Embed inserts crash `expected vector(1024)` | `EMBEDDING_DIM` in `.env` doesn't match the actual embedder output. BGE-small is 384-dim. | Set `EMBEDDING_DIM=384`, drop the `chunk` table, re-migrate, re-upload. |
| Source stuck at `embedding` | Worker started with `arq` CLI instead of `python -m pynote_worker` on Windows — Proactor loop kills psycopg3. | Use `just worker` (or `uv run python -m pynote_worker`). |
| Outline 401 | `get_cheap_model()` fell back to Anthropic Haiku without a working Anthropic key. | Set `GOOGLE_API_KEY` so the cheap path uses Gemini Flash. |
| `relation "chunk" does not exist` | Migration `0003_chunks` hasn't run. | `just migrate`. If alembic is desynced, `alembic stamp 0002 && alembic upgrade head`. |

## License

MIT.
