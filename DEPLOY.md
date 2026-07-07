# PyNote — Free-Tier Cloud Deploy Plan

> Companion to [COSTS.md](COSTS.md) (providers) and [SHIP.md](SHIP.md) (demo runbook).
> Goal: the full stack — web, api, worker, Postgres, Redis, object storage — running on
> $0/month managed services, reachable at a public URL. Cold starts accepted; scale not.

## 1. Target topology

```
Browser ── Vercel (apps/web, Next.js 15 + Clerk)
              │  fetch / SSE  (direct browser → API, no Vercel proxy)
              ▼
         Render free web service #1 (apps/api, Docker)
              │  enqueue arq
              ▼
         Render free web service #2 (apps/worker + tiny health port)
              │
   Neon Postgres (pgvector)   Upstash Redis   Cloudflare R2
```

| Piece | Service | Free tier | Why this one |
|---|---|---|---|
| Web | **Vercel Hobby** | 100 GB bandwidth/mo | Native Next.js 15; ignores `apps/web/Dockerfile` entirely |
| API | **Render free web service** (Docker) | 512 MB RAM, sleeps after 15 min idle | Supports SSE streaming + Docker; free background workers don't exist, web services do |
| Worker | **Render free web service** (Docker + dummy health port) | 512 MB RAM | Render's "Background Worker" type is paid-only; a web service that also binds `$PORT` is the standard workaround |
| Postgres | **Neon free** | 0.5 GB storage, scale-to-zero | `vector`, `pg_trgm`, `btree_gin` all available; no 7-day pause-and-restore dance like Supabase free |
| Redis (arq) | **Upstash free** | 256 MB, **500k commands/month** | Only serverless Redis free tier; see §4 for the poll-rate landmine |
| Object storage | **Cloudflare R2** | 10 GB, $0 egress | S3-compatible, works with existing `S3_*` settings. Requires a card on file — if that's a blocker, Backblaze B2 (10 GB, no card) is also S3-compatible |
| Auth | **Clerk dev instance** (existing) | 10k MAU | `pk_test_` keys work on any origin incl. `*.vercel.app`; a *production* Clerk instance needs a custom domain — skip for free tier |
| LLM / rerank | unchanged | — | Anthropic key, Gemini free tier, Voyage free tier — same as [COSTS.md](COSTS.md) §3a |

## 2. Code changes required first (small, all config-shaped)

1. **CORS** — `apps/api/src/pynote_api/main.py` hardcodes `allow_origins=["http://localhost:3000"]`.
   Add a `WEB_ORIGIN` (or comma-separated `CORS_ORIGINS`) setting to `pynote_core.settings` and read it there.
   Without this every browser call from Vercel fails preflight.
2. **arq poll rate** — `apps/worker/src/pynote_worker/main.py` `WorkerSettings` uses arq's default
   `poll_delay=0.5s`. That's ~2 Redis commands/second ≈ **5M commands/month against Upstash's 500k free quota**
   — quota gone in ~3 days. Add:
   ```python
   poll_delay: ClassVar[float] = 5.0          # seconds; ingest latency +5s is invisible
   health_check_interval: ClassVar[int] = 300
   ```
3. **Worker health port** — Render free services must bind `$PORT` or get killed. Either add a
   ~10-line aiohttp/`http.server` thread to `pynote_worker.__main__`, or set the Render start command to:
   ```
   sh -c "python -m http.server ${PORT:-8080} & python -m pynote_worker"
   ```
4. **Bake the embedding model into the worker image** — fastembed downloads BGE-small (~130 MB) to an
   ephemeral disk on every cold boot, so the first ingest after each sleep re-downloads it. Add to
   `apps/worker/Dockerfile`:
   ```dockerfile
   RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
   ```
   (If the API also embeds queries for hybrid search, do the same in `apps/api/Dockerfile`.)
5. **Concurrency down** — set `WORKER_CONCURRENCY=1` in the worker env. 512 MB doesn't fit
   4 parallel PyMuPDF + embedding jobs.

## 3. Provisioning steps (in order)

### 3.1 Neon Postgres
1. neon.tech → new project → region close to Render region (e.g. `aws-us-east-1` ↔ Render Oregon/Ohio — pick matching regions for both).
2. `CREATE EXTENSION vector; CREATE EXTENSION pg_trgm; CREATE EXTENSION btree_gin;` (Neon allows all three from SQL editor).
3. Run migrations **from your machine** against the Neon URL (simplest — no release phase on free tier):
   ```bash
   DATABASE_URL="postgresql+psycopg://...neon.tech/pynote?sslmode=require" uv run alembic upgrade head
   ```
4. Keep `EMBEDDING_DIM=384` — the migration reads it at runtime, and 384-dim keeps you inside 0.5 GB.

### 3.2 Upstash Redis
1. upstash.com → new database, same region.
2. Copy the **`rediss://`** URL (TLS) → `REDIS_URL`. `RedisSettings.from_dsn` handles `rediss://`.
3. Do **not** deploy the worker before the §2.2 `poll_delay` change lands.

### 3.3 Cloudflare R2 (or Backblaze B2)
1. Create bucket `pynote-sources`, generate an S3 API token.
2. Env mapping: `S3_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com`, `S3_REGION=auto`,
   `S3_FORCE_PATH_STYLE=true`, keys from the token, `S3_BUCKET=pynote-sources`.
3. No public access needed — the API streams files back itself via `/sources/{id}/file`.

### 3.4 Render — API service
1. New Web Service → connect the GitHub repo → runtime **Docker**, dockerfile path `apps/api/Dockerfile`,
   docker context `.` (repo root — the Dockerfile copies `packages/core`).
2. Instance type **Free**. Health check path: `/api/v1/health` (or whatever `routes/health.py` exposes).
3. Env vars: `DATABASE_URL` (Neon, with `?sslmode=require`), `REDIS_URL` (Upstash `rediss://`), all `S3_*` (R2),
   `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `PROVIDER_TIER`, `EMBEDDING_DIM=384`, `CLERK_JWKS_URL`,
   `CLERK_SECRET_KEY`, `ENVIRONMENT=production`, `WEB_ORIGIN=https://<app>.vercel.app` (new, §2.1).
4. Note the URL: `https://pynote-api.onrender.com`.

### 3.5 Render — worker service
1. Second free Web Service, same repo, dockerfile `apps/worker/Dockerfile`, context `.`.
2. Start command override with the health-port trick (§2.3) until it's in the image.
3. Same env vars as the API minus Clerk/CORS, plus `WORKER_CONCURRENCY=1`.
4. ⚠️ Free services sleep after 15 min idle — **a sleeping worker processes nothing**. An upload enqueued
   while the worker sleeps sits in Redis until the worker wakes. Options:
   - Accept it for demos: open the Render dashboard → "Resume" before demoing, or
   - Have the API ping the worker's health URL when it enqueues (1-line `httpx.get` fire-and-forget), which wakes it.
5. Render free tier is 750 instance-hours/month pooled — two always-awake services would exceed it,
   but with idle sleep a demo workload stays well inside.

### 3.6 Vercel — web
1. Import repo → root directory `apps/web` → framework preset Next.js (the Dockerfile is ignored; that's fine).
2. Env vars: `NEXT_PUBLIC_API_URL=https://pynote-api.onrender.com`,
   `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_…`, `CLERK_SECRET_KEY=sk_test_…`.
3. Clerk dashboard → the dev instance already accepts any origin, so `https://<app>.vercel.app` sign-in
   works with `pk_test_` keys. (Custom domain + production instance is the paid-polish upgrade, not needed.)

## 4. Free-tier landmines (ranked by how certainly they bite)

| # | Landmine | Effect | Mitigation |
|---|---|---|---|
| 1 | arq default 0.5s poll vs Upstash 500k cmd/mo | Redis quota exhausted in ~3 days, ingest dies | `poll_delay=5.0` (§2.2) — **do this before first deploy** |
| 2 | Worker asleep when upload arrives | Source stuck at `queued` | Wake-ping from API or manual resume pre-demo (§3.5) |
| 3 | Render cold start (~30–60 s Docker boot) | First request after idle hangs; SSE chat appears dead | Warm both services 10 min before a demo (add to SHIP.md checklist); optional UptimeRobot ping every 10 min *during demo windows only* (24/7 pinging burns the 750 h pool) |
| 4 | 512 MB RAM on API+worker | OOM kill mid-embed | `WORKER_CONCURRENCY=1`, BGE-small (not M3), avoid >50 MB PDFs |
| 5 | Neon scale-to-zero (~500 ms wake) | First query slow, harmless | Nothing needed |
| 6 | BGE model re-download per cold boot | First ingest after sleep +60 s | Bake model into image (§2.4) |
| 7 | Gemini 2.5 Pro 50 RPD | Summary 429s | Already handled — `GEMINI_MODEL_HEAVY=gemini-2.0-flash` or `PROVIDER_TIER=prod` |

## 5. Smoke test (after all six pieces are up)

```bash
curl https://pynote-api.onrender.com/api/v1/health          # wakes API; expect 200
# then in the browser at https://<app>.vercel.app:
#  sign in → create notebook → upload small PDF → pill reaches "ready"
#  → chip → chat streams → citation pill opens the PDF drawer
uv run python -m eval.prototype.m3 health                   # with cloud DATABASE_URL exported
```

## 6. Explicit non-goals of the free deploy

- No custom domain / production Clerk instance (needs a domain purchase).
- No always-on worker (paid Render worker, $7/mo, is the first upgrade if ingest latency matters).
- No CI-driven deploys — Render and Vercel both auto-deploy on push to `master`, which is enough.
- Secrets live in the Render/Vercel dashboards, never in git. Rotate any key that has ever left `.env`.
