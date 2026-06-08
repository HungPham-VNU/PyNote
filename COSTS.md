# PyNote — Cost & Provider Configuration

> Companion to [PLAN.md](PLAN.md). The plan defines *what* we're building; this doc defines *which providers* we use to pay for it.
>
> **🛑 Post-mortem update (2026-06-07):** the "Claude via GitHub Models" path documented below **does not work** with `langchain-anthropic`. The Anthropic SDK ships the API key as `x-api-key`; the GH Models endpoint expects `Authorization: Bearer`. v1 actually ships on a **real Anthropic API key** using the $5 signup credit. The original guidance is preserved below with a strikethrough so the history is honest, and §3a + §11 record what we actually use.

---

## 1. The university-project constraint

| Constraint | Implication |
|---|---|
| Solo / small team, 1 semester | Build with free tiers; expect rate-limit speed-bumps |
| Demos > production scale | Concurrency caps OK; latency caps NOT OK during a demo |
| Budget ~$0 | No ElevenLabs Pro, no Anthropic prepaid, no managed Postgres |
| Reusable as portfolio | Stack should be swappable to paid providers in <1 day |

This doc keeps the **architecture from PLAN.md unchanged** and only swaps the *providers* per layer.

---

## 2. Verified API pricing (May 2026)

Useful as the reference for "what would this cost if I paid." Source: claude.com/pricing, docs.voyageai.com.

| Model | Input | Cache write (5m) | Cache read | Output |
|---|---|---|---|---|
| Claude Opus 4.7 | $5 / MTok | $6.25 | $0.50 | $25 |
| Claude Sonnet 4.6 | $3 / MTok | $3.75 | $0.30 | $15 |
| Claude Haiku 4.5 | $1 / MTok | $1.25 | $0.10 | $5 |
| Voyage-3-large embeddings | $0.18 / MTok | — | — | — |
| Voyage rerank-2.5 | $0.05 / MTok | — | **first 200M tok/mo FREE** | — |

> **Notable**: Opus 4.5+ is **3× cheaper** than Opus 4.1 was. Even paid, Opus is now reasonable for artifact generation.
> **Claude Pro ≠ API access.** Your $20/mo Pro plan covers claude.ai + Claude Code (used for *writing* PyNote), but not API calls *PyNote itself* makes at runtime.

---

## 3a. What v1 actually ships on (the truth, post-build)

After three rounds of debugging the GH Models path, this is the config that demoably works:

| Layer | Provider | Cost | Notes |
|---|---|---|---|
| **Chat LLM (citations)** | **Anthropic API direct** (`sk-ant-…`) | ~$0.02 / chat turn | $5 signup credit covers ~250 turns. No `ANTHROPIC_BASE_URL` set. |
| **Cheap LLM (outline)** | Gemini 2.0 Flash (`get_cheap_model()`) | $0 | 1500 RPD free tier. `GOOGLE_API_KEY` from aistudio.google.com |
| **Heavy LLM (summary)** | Gemini 2.0 Flash *or* Claude Opus 4.7 | $0 (Flash) / ~$0.08 (Opus) | `PROVIDER_TIER=prod` routes summary to Opus. `GEMINI_MODEL_HEAVY=gemini-2.0-flash` to stay free. Do NOT use `gemini-2.5-pro` for demos — 50 RPD hits in minutes. |
| **Embeddings** | fastembed `BAAI/bge-small-en-v1.5` (local) | $0 | 384-dim, ~130 MB ONNX. Must set `EMBEDDING_DIM=384` in `.env`. |
| **Rerank** | Voyage rerank-2.5 (optional) | $0 (200M tok/mo free) | Falls back gracefully to top-K hybrid if not set. |
| **Vector DB / sparse** | pgvector + tsvector in Postgres | $0 | Local Docker |
| **Object storage (dev)** | MinIO in Docker | $0 | |
| **Auth** | Clerk free tier | $0 | 10k MAU |
| **Observability** | LangSmith hobby | $0 | 5k traces/mo |

Total runtime cost for a demo: well under $1.

A handful of `temperature` / model-name corrections also landed in the LLM factory — see the troubleshooting table in [README.md](README.md) and [SHIP.md](SHIP.md) for the specific gotchas.

---

## 3. Original free-tier stack (the broken plan)

The grid below is **historical** — keep it for the architecture diff, but ignore the "Chat LLM via GitHub Models" row.

| Layer | Free choice | Quota | Notes |
|---|---|---|---|
| ~~**Chat LLM (citation-critical)**~~ | ~~**Claude Sonnet 4.6 via GitHub Models**~~ | ~~~150 RPM, 150k TPM~~ | ❌ **Broken** — `langchain-anthropic` sends `x-api-key`, GH Models wants `Authorization: Bearer`. Use real `sk-ant-…` instead (§3a). |
| **Light LLM ops** (rewrite/classify/outline) | **Gemini 2.0 Flash** (Google AI Studio) | 1,500 RPD, 1M TPM | Generous; ~free forever |
| **Heavy LLM** (artifacts in v2+) | **Gemini 2.5 Pro** (Google AI Studio free) | 50 RPD | Rate-limited but fine for demos |
| **Embeddings** | **`text-embedding-004`** via Gemini API OR **`BAAI/bge-m3`** local | Gemini: very high free TPM. BGE: unlimited local. | BGE-M3 wins on multilingual + offline; pick one |
| **Rerank** | **Voyage rerank-2.5** | 200M tok/mo *free forever* | ~13,000 reranks/mo free. Keep from PLAN.md |
| **Vision (figure captions)** | Gemini 2.0 Flash vision | Same free tier | Replaces Sonnet vision pass |
| **ASR** (audio sources) | **faster-whisper** large-v3, local | Unlimited | CPU works for short clips; Colab GPU for batch |
| **TTS** (Audio Overview, v3) | **Microsoft Edge TTS** OR **Coqui XTTS-v2** local | Free, unlimited | Edge TTS = good prosody, no install; Coqui = better voices, local model |
| **Vector DB** | pgvector | Free | Unchanged from PLAN.md |
| **Sparse retrieval** | Postgres tsvector | Free | Unchanged |
| **Object storage (dev)** | MinIO via docker-compose | Free | Unchanged |
| **Object storage (deployed demo)** | Cloudflare R2 | 10 GB-mo free, $0 egress | Free for any class-size demo |
| **Postgres (deployed demo)** | Supabase free OR Neon free | 500 MB – 3 GB | Either fine; Supabase Auth is a side benefit |
| **Redis (deployed demo)** | Upstash free | 10k commands/day, 256 MB | More than enough |
| **Auth** | Clerk free tier | 10,000 MAU, 100 orgs | Unchanged from PLAN.md |
| **Observability** | LangSmith hobby | 5,000 traces/mo | Or self-host Langfuse via docker-compose |
| **Hosting (demo day)** | localhost + Cloudflare Tunnel/ngrok | Free | Or Fly.io free Postgres + free machine |
| **Hosting (always-on)** | Render free web service + Supabase | $0 (with cold starts) | Fly.io free tier shut down some perks; check current limits |

---

## 4. The Citations API problem (and three answers)

Anthropic's Citations API is the single feature the whole PLAN.md architecture is built around. Gemini doesn't have a true equivalent for *document* citations (its grounding is tied to Google Search). Three viable paths:

### ~~Path A — Claude via GitHub Models~~ ❌ Doesn't work

We pitched this as the recommended free path. In reality:

- GitHub Models at `https://models.inference.ai.azure.com` is the **Azure AI Inference** dialect, which expects `Authorization: Bearer <PAT>` or an `api-key` header.
- `langchain-anthropic` always emits `x-api-key: <token>` because it wraps the official `anthropic` Python SDK.
- The endpoint sees neither expected auth header and returns:
  ```
  401 - "No authorization header or api key found in request."
  ```

Two ways forward:

1. **Recommended now**: use the **real Anthropic API** with a `sk-ant-…` key. Sign up at console.anthropic.com → $5 free credit on signup → covers all of a demo with room to spare. Unset `ANTHROPIC_BASE_URL` (so the SDK defaults to `https://api.anthropic.com`).
2. **If you must use GH Models**: switch from `langchain-anthropic` to `langchain-openai`'s `ChatOpenAI` pointing at `https://models.github.ai/inference` (OpenAI-compat shape, accepts Bearer). You lose Anthropic's Citations API in the process, which defeats the whole architecture. Not recommended.

```python
# What actually works in llm.py today:
ChatAnthropic(
    model="claude-sonnet-4-6",
    api_key=os.environ["ANTHROPIC_API_KEY"],   # sk-ant-...
    max_tokens=4096,
    # NO base_url, NO temperature (Opus 4+ rejects it).
)
```

Original (broken) path details below for reference:
- ✅ $0
- ⚠️ Rate-limited (varies by your GH plan; free is ~10 RPM, Copilot Pro ~150 RPM)
- ⚠️ TOS: "for evaluation and experimentation" — fine for a university project, not for a commercial product

### Path B — Gemini Flash + post-hoc citation mapping

Gemini answers, then a small post-processor maps each answer sentence back to a source span:

```
for each sentence in answer:
    candidates = top-3 chunks by cosine(embed(sentence), chunk.embedding)
    best = highest ROUGE-L overlap among candidates
    if rouge_l(sentence, best.text) > 0.4:
        cite (best.source_id, best.char_start + match_offset, ...)
```

- ✅ $0, no rate limits beyond Gemini free tier
- ✅ Reliable, no third-party flakiness
- ⚠️ Citation fidelity ~10-15% lower than Anthropic Citations API on hand-graded set
- ✅ Still demoable; the gap won't be obvious to non-experts

### Path C — Anthropic free $5 credits + tight rationing

New Anthropic accounts get ~$5 in free credits. Sonnet at $3/$15 = roughly **200 grounded chat turns** before you'd hit zero.

- ✅ Production-grade Citations API
- ⚠️ One-time only; no ongoing budget
- 🎯 Best used as fallback for demo day, not primary

### Recommendation: **Hybrid (A + B fallback)**
- Default to Claude via GitHub Models for the chat-generation node.
- On rate-limit or 429, gracefully fall back to Gemini + post-hoc citations.
- Log fallback frequency in LangSmith; if it's high, request GH Models higher tier or top up $5 of Anthropic.

LangChain makes this easy — the chat node uses a [`with_fallbacks`](https://docs.langchain.com/oss/python/integrations/chat/anthropic) Runnable.

```python
chat_model = (
    ChatAnthropic(model="claude-sonnet-4-6", anthropic_api_url=GH_MODELS_URL, ...)
    .with_fallbacks([ChatGoogleGenerativeAI(model="gemini-2.0-flash")])
)
```

---

## 5. Stack swaps relative to PLAN.md

| Layer | PLAN.md (production) | University free-tier |
|---|---|---|
| Chat (grounded) | `langchain-anthropic` direct | `langchain-anthropic` → **GitHub Models endpoint** |
| Cheap ops | Haiku 4.5 | **Gemini 2.0 Flash** (`langchain-google-genai`) |
| Heavy artifacts (v2) | Opus 4.7 | **Gemini 2.5 Pro** (free, 50 RPD cap) |
| Embeddings | Voyage-3-large | **`text-embedding-004`** OR **BGE-M3 local** |
| Rerank | Voyage rerank-2.5 | **same** ← already free up to 200M tok/mo |
| Vision figures | Sonnet vision | Gemini Flash vision |
| TTS (v3) | ElevenLabs v3 | **Edge TTS** (`edge-tts` pip) or **Coqui XTTS-v2** |
| ASR (v2) | Deepgram or faster-whisper | faster-whisper (unchanged) |
| Hosting | Fly/Railway/AWS | localhost + Tunnel for demo days |
| Postgres | RDS/managed | Supabase/Neon free OR local Docker |

Architecture, milestones, and code structure from PLAN.md are otherwise **unchanged**. The provider layer is the only thing swapped, isolated in `apps/api/deps/`.

---

## 6. Monthly cost estimate

### Pure free path
| Item | $/mo |
|---|---|
| Anthropic via GH Models | $0 |
| Gemini API | $0 |
| Voyage rerank | $0 (200M-tok free tier) |
| Voyage embeddings (if used) | $0 (200M-tok signup credits last months) |
| TTS (Edge / Coqui) | $0 |
| ASR (faster-whisper local) | $0 |
| Auth (Clerk free) | $0 |
| Hosting (local + tunnel, or Render free) | $0 |
| Postgres (Supabase free) | $0 |
| Redis (Upstash free) | $0 |
| Object store (R2 free tier) | $0 |
| LangSmith hobby | $0 |
| **Total** | **$0** |

### Demo-day burst budget (optional, one-time)
| Item | $ |
|---|---|
| Anthropic top-up (Sonnet, ~500 chats) | $5–10 |
| ElevenLabs free tier (10k chars/mo ≈ 10 audio overviews) | $0 |
| Custom voice on ElevenLabs (if you want better Audio Overview) | $5/mo (Creator) |
| Optional: Voyage embeddings if BGE-M3 underperforms | $1–2 |
| **Total** | **~$10–20** |

### What blows the budget (avoid)
- Running paid LLM ops in a loop during dev. Always test with cached fixtures.
- Letting Audio Overview generation be unrestricted. Cap to "1 per user per day."
- Mind-map / study-guide regen storms while iterating prompts. Snapshot, don't regen.

---

## 7. Cost-control patterns (apply from M0)

1. **Prompt cache on the notebook prefix.** Long conversations share the same notebook context. Cache write costs 1.25× but each subsequent turn reads at 0.1×. Pays off after the second turn.
2. **Batch the slow stuff** (artifacts, summarization). Anthropic Batch API = 50% discount, runs within 24h. Free tier–compatible because it's just slower.
3. **Cap top-K aggressively in retrieval.** 8 reranked chunks is enough; don't pass 20.
4. **Compress conversation history.** Roll up old turns into a one-sentence summary after the 6th turn.
5. **Cache TTS clips by `hash(voice, text)`.** Re-listening to an Audio Overview should be free.
6. **Eval against a fixed seed set + recorded golden answers.** Don't run live LLM calls in CI on every PR — replay cassettes (vcrpy) + nightly real evals.
7. **Disable autocomplete-style features** during dev (suggested questions, auto-summary on upload). Toggle on for demos.
8. **Per-user/notebook quotas from M0**, even on free tier — they double as anti-runaway-cost guards.

---

## 8. What to do on demo day

Switch a `.env` flag `PROVIDER_TIER=demo` that:
1. Routes chat to **Anthropic API direct** (use ~$5 of pre-loaded credit) instead of GH Models — eliminates rate-limit risk.
2. Bumps Gemini calls to Gemini 2.5 Pro for heavier artifacts.
3. Enables ElevenLabs creator-grade voice for Audio Overview (if used).
4. Disables LangSmith trace sampling — you want every demo turn captured.

Cost: ~$5–10 for a 3-hour demo window with 50 chats and 5 audio overviews.

After demo: flip back to free tier.

---

## 9. Compromises you accept on the free path

| Feature | Compromise |
|---|---|
| Citation fidelity | ~5–15% lower if Gemini fallback path triggers (B) vs Claude direct |
| Concurrency | Can't serve >2–5 simultaneous users during peak |
| Audio Overview voice quality | Edge TTS is good but distinctly less natural than ElevenLabs v3 |
| Heavy artifact throughput | Gemini 2.5 Pro at 50 RPD limits study-guide generation to ~5 students/day |
| First-token latency | Cold-start on free hosts (Render/Supabase) adds 2–5s on first hit after idle |

None of these prevent a working, demoable, NotebookLM-class application. They prevent *scaling*.

---

## 10. Upgrade path (when you stop being a student)

When/if PyNote moves beyond university:
- Flip `PROVIDER_TIER` to `prod` → routes to paid Anthropic + Voyage + ElevenLabs.
- Move Postgres from Supabase free to Supabase Pro or RDS.
- Add monitoring quotas, payment integration (Stripe), enterprise features per PLAN.md §M16-M17.

The whole switch is config + a credit card, because the architecture didn't change.

---

## 11. Final decision (updated after the build)

What v1 actually ships on — replacing the original plan in §11:

1. **Real Anthropic API (`sk-ant-…`)** for chat and any heavy-mode summary. $5 signup credit, no card on file required. Citations API works end-to-end. Do not set `ANTHROPIC_BASE_URL`.
2. **Gemini 2.0 Flash** (`GOOGLE_API_KEY` from aistudio.google.com) for outline + cheap-tier summary. Free, 1500 RPD.
3. **`BAAI/bge-small-en-v1.5` (384-dim) via fastembed**, local. The original plan said BGE-M3 (1024-dim); we downgraded to BGE-small to keep the Windows demo machine snappy. **`EMBEDDING_DIM=384`** must be set in `.env` to match the schema migration.
4. **Voyage rerank-2.5** (optional, 200M tok/mo free) — used when `VOYAGE_API_KEY` is set, falls back to top-K hybrid otherwise.
5. **`PROVIDER_TIER=prod`** in `.env` — routes the summarizer to Opus via Anthropic (not Gemini 2.5 Pro, which has a 50 RPD cap that hit during testing).
6. **Local docker-compose** for Postgres / Redis / MinIO. No paid hosting.
7. **Total runtime cost for the demo: well under $1.** The $5 Anthropic credit is the only money on the table.

Total deviation from the original plan: 1 broken provider path (GH Models), 1 model swap (Opus instead of Gemini 2.5 Pro on free tier), 1 embedding-dim downgrade (384 instead of 1024). Architecture unchanged.

Cost: **$0/month, ~$10 total over the semester.**
