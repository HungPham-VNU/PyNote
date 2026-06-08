# Shipping v1 — runbook + grader cheat sheet

This is the page to read first. v1 is built. This document explains what's there, how to verify it works, and what to do if something stalls.

## v1 surface

What a grader / reviewer sees in one session:

- Multi-user, Clerk-org-scoped Next.js 15 web app on a **dark Material-3 theme**.
- Upload PDF → parsed → embedded → outlined, end-to-end via arq worker.
- Suggested-question chips appear once outline finishes.
- Click a chip → it autofills the chat input.
- Send a question → tokens stream via SSE through a LangGraph pipeline.
- Citation pills `[1] [2]` render inline.
- Click a pill → slide-over PDF viewer opens at the cited page with the span highlighted in yellow.
- Refresh page → conversation reloads from `PostgresSaver` thread state.
- Click "Generate summary" → second slide-over drawer with `{headline, key_points[3..7], detailed_summary}`.

## The ship gate

```bash
uv run python -m eval.run --notebook YOUR_NB --file eval/golden/sample.jsonl \
  > eval/results/v1-$(date +%s).jsonl
jq 'select(._summary)' eval/results/v1-*.jsonl | tail -1
```

Pass when the final `_summary` line shows `"passed": true`. Thresholds:

| Metric | Gate | What it measures |
|---|---|---|
| `citation_grounding` | ≥ 0.90 | Fraction of Anthropic citations whose `(start_char, end_char)` resolve to the exact chunk substring |
| `faithfulness_lite` | ≥ 0.60 | Cheap proxy — answer tokens also present in retrieved contexts |
| `answer_relevancy_lite` | ≥ 0.25 | Cheap proxy — token overlap between question and answer |

Exit code === gate verdict. Add `--with-ragas` for the LLM-judge metrics if `uv pip install --group eval` ran first.

## Demo script (90 seconds)

Time the steps so the demo lands at a "wow" moment.

| t | Action | What grader sees |
|---|---|---|
| 0:00 | Sign in via Clerk | Dark Material-3 dashboard with org switcher |
| 0:10 | Create "Course readings" notebook | Indigo CTA, blank workspace renders |
| 0:25 | Drag-drop a PDF | Status pill cycles `parsing → embedding → ready` (~30 s) |
| 0:55 | Click a "Try asking…" chip | Autofills chat input |
| 1:05 | Send | Tokens stream into a dark assistant bubble, 3 citation pills appear |
| 1:20 | Click `[1]` | Slide-over PDF opens at the right page, yellow span visible |
| 1:35 | Close drawer, click "Generate summary" | Yellow CTA → second drawer with headline + bullet points |

End on the summary drawer or the highlight — both are the visible payoff of the architecture.

## Pre-demo checklist (run 10 minutes before)

```bash
# 1. Services healthy
docker compose -f docker-compose.dev.yml ps   # all three "healthy"

# 2. Code green
just test                                      # 60 passed, 2 skipped

# 3. Providers reachable + key loaded
uv run python -m eval.prototype.m3 health
# expect: anthropic_key=set, google_api_key=set, postgres=ok, chunks_total>0
```

If `chunks_total = 0`, upload your demo PDF NOW — the first ingest pre-warms the BGE-small download (~130 MB, one-time).

## Required env (the ones that actually matter)

The provider story changed during build — these are what works on demo day:

```bash
# Anthropic — REAL key, $5 free credit covers a demo
ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXX
# (Leave ANTHROPIC_BASE_URL UNSET — the GitHub Models route is broken with langchain-anthropic)

# Gemini — free tier
GOOGLE_API_KEY=AIzaSyXXXXXXXX
GEMINI_MODEL_HEAVY=gemini-2.0-flash    # NOT gemini-2.5-pro (50/day limit)

# Embeddings — must match the actual model output
EMBEDDING_DIM=384                       # BGE-small produces 384-dim

# Provider routing
PROVIDER_TIER=prod                      # uses Claude for summary; "free" uses Gemini

# Clerk (Organizations enabled, Personal accounts disabled)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
CLERK_JWKS_URL=https://<your>.clerk.accounts.dev/.well-known/jwks.json
```

## Things that go wrong + their fixes

| Symptom | Where to look | Fix |
|---|---|---|
| Web 500 on dashboard | api terminal — full traceback | Usually `relation "chunk" does not exist` → `just migrate` |
| Chat returns `401 - No authorization header` | Stripped of GH Models, set `sk-ant-…` key and unset `ANTHROPIC_BASE_URL`, restart api |
| Summary returns `temperature is deprecated` | Already fixed in `_anthropic_kwargs` — pull latest changes, restart api |
| Summary returns 429 | Gemini 2.5 Pro is 50/day | Switch `GEMINI_MODEL_HEAVY=gemini-2.0-flash` or set `PROVIDER_TIER=prod` |
| Source stuck at `embedding` | worker terminal | Restart worker with `just worker` (NOT raw `arq` CLI — breaks on Windows) |
| Outline 401 | `cheap_model` falling back to Anthropic Haiku with no working Anthropic key | Set `GOOGLE_API_KEY` so Gemini Flash handles outline |
| Embed insert crash with `expected vector(N)` | `.env` `EMBEDDING_DIM` ≠ what fastembed actually produces | Set `EMBEDDING_DIM=384`, `DROP TABLE chunk`, re-migrate, re-upload |
| PDF won't open in drawer | Browser DevTools → Network on `/sources/{id}/file` | 401 means Clerk token expired — refresh page |
| Yellow highlight missing | Firefox or unsupported browser | Demo in Chrome / Edge / Safari — Custom Highlight API |
| Delete button doesn't work | Some FK cascade edge case | Bypass via SQL: `DELETE FROM chunk WHERE source_id='...'; DELETE FROM source_part ...; DELETE FROM source ...` |

## What's intentionally out of v1

Per the original PLAN.md beyond M7, these are the original roadmap items deferred:

- **Multi-source ingestion** (DOCX, URL, YouTube, audio, image) — M8
- **Notes as first-class sources** — M9
- **More artifact types** (FAQ, study guide, mind map, audio overview) — M10–M13
- **Vision RAG, sharing, RLS, BYOK** — M14–M17

The summary artifact and the dark-theme redesign were added post-v1 as the highest "demo wow ÷ build time" choices.

## What I'd do next if shipping past the university milestone

1. **Web URL ingestion** — easiest second source type. `trafilatura` + existing chunker.
2. **Save chat answer as note** — closes the loop; notes become indexable sources.
3. **Switch `temperature` handling per-model** — currently dropped globally; Sonnet/Haiku still accept it.
4. **Real golden set** — replace `eval/golden/sample.jsonl` with notebook-specific Q/As for honest grading.
5. **Cascade-delete FK** on chunk → source so the UI delete button works without the SQL workaround.
