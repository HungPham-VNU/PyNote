# RAG Pipeline Optimization — Roadmap & Implementation Guide

> Companion to [PLAN.md](PLAN.md) (feature milestones). This document covers the
> **retrieval/generation quality track**: input-pipeline (ingestion) and
> output-pipeline (query → generation → citations) optimizations, ordered by
> impact-per-effort. Written 2026-07-07 from a review of the shipped v1.
>
> **Invariant that every change below must preserve** — the citation contract:
> `source_part.text[chunk.char_start : chunk.char_end] == chunk.text`, and
> `hits[i]` stays aligned with the `search_result` block at index `i`
> (see [packages/core/src/pynote_core/citations.py](packages/core/src/pynote_core/citations.py)).

---

## Current state (what v1 does today)

```
INGEST   PyMuPDF per-page text → flat 1200-char windows (200 overlap)
         → bge-small-en-v1.5 (384-dim, no query prefix) → pgvector + tsvector('english')

QUERY    raw question (+ selected_text concat) → hybrid RRF CTE (50 dense / 50 sparse)
         → Voyage rerank-2.5 → top 8

GENERATE search_result blocks → Claude Citations API → char-offset roundtrip
         → SSE stream; full history accumulates; citations kept for last turn only
```

Grade: the **grounding layer is production-quality**; the **parser/chunker are
the most naive possible**; **multi-turn retrieval is broken by design** (no
query rewriting). Fix order below reflects that.

---

## Phase overview

| Phase | Theme | Effort | Items |
|---|---|---|---|
| 1 | Cheap, high-impact fixes | ~days | Query rewriting, BGE query prefix, shared checkpointer pool, prompt caching, overlap dedup, history trimming |
| 2 | Persistence & measurement | ~1 week | Per-message citations, retrieval-level eval (recall@k / MRR), parser hygiene |
| 3 | Structural upgrade | 1–2 weeks | Docling structure parsing, contextual embeddings, embedding model upgrade |
| 4 | Differentiation | ongoing | Source-scoped retrieval, query routing, vision RAG |

**Rule for phases 3–4: land Phase 2's retrieval eval first.** Every structural
change after that gets a before/after recall@k number, not vibes.

---

## Phase 1 — Cheap, high-impact (target: one sprint)

### 1.1 Query rewriting for multi-turn ⭐ highest impact

**Problem.** `node_retrieve` ([chat_graph.py:75](packages/core/src/pynote_core/chat_graph.py#L75))
retrieves on the raw question. Turn-2 questions like *"what about the second
method?"* retrieve garbage; the model (correctly instructed to answer only from
search results) replies "not in the sources" and the product feels broken.

**Design.** New graph node `rewrite` between `START` and `retrieve`:

- Turn 1 (no prior messages in state): skip — pass the question through unchanged.
- Turn 2+: one `get_cheap_model()` (Gemini Flash) call condensing the last
  ~6 messages + new question into a standalone search query.
- On any model failure: fall back to the raw question (never block the turn).

**Implementation sketch** (`packages/core/src/pynote_core/chat_graph.py`):

```python
class ChatState(TypedDict, total=False):
    ...
    search_query: str  # transient: standalone query produced by rewrite

_REWRITE_PROMPT = (
    "Rewrite the user's latest question as a single standalone search query, "
    "resolving pronouns and references using the conversation. Return ONLY the "
    "query text.\n\nConversation:\n{history}\n\nLatest question: {question}"
)

async def node_rewrite(state: ChatState) -> dict[str, Any]:
    question = state["question"]
    history = state.get("messages") or []
    if not history:
        return {"search_query": question}
    transcript = "\n".join(
        f"{'user' if isinstance(m, HumanMessage) else 'assistant'}: {_flatten(m.content)[:400]}"
        for m in history[-6:]
    )
    try:
        model = get_cheap_model()
        resp = await model.ainvoke(
            [HumanMessage(content=_REWRITE_PROMPT.format(history=transcript, question=question))]
        )
        rewritten = str(resp.content).strip()
        return {"search_query": rewritten or question}
    except Exception:
        return {"search_query": question}
```

Then in `node_retrieve`, retrieve **and rerank** on `state["search_query"]`
(this also fixes the current inconsistency where hybrid uses
selection+question but rerank uses the bare question). Wire:
`START → rewrite → retrieve → generate → map_citations → END`.

**Acceptance.** Add 5+ multi-turn cases to the golden set (a turn-1 question,
then a pronoun-heavy follow-up); the follow-up's retrieved chunk set must
contain the same gold chunk as an explicitly-worded version of the question.

---

### 1.2 BGE query prefix (asymmetric embedding)

**Problem.** BGE models are trained asymmetrically: queries need the
instruction prefix *"Represent this sentence for searching relevant passages: "*;
passages are embedded plain. [embeddings.py](packages/core/src/pynote_core/embeddings.py)
uses the same `embed_many` path for both, silently losing recall.

**Implementation.** Split the protocol into document vs query paths; fastembed
already exposes `query_embed` which applies the correct prefix for BGE:

```python
class Embedder:
    dim: int
    async def embed_many(self, texts): ...      # documents (unchanged)
    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_many([text]))[0]   # default: symmetric

class _FastembedBGE(Embedder):
    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(lambda: list(self._model.query_embed([text])))
        return list(map(float, vectors[0]))
```

Call site: `hybrid_retrieve` ([retrieval.py:92](packages/core/src/pynote_core/retrieval.py#L92))
switches `embed_one` → `embed_query`. **Document vectors don't change — no
re-embedding, no migration.**

---

### 1.3 Long-lived checkpointer pool

**Problem.** Every chat request and every history fetch runs
`open_chat_graph()` → `AsyncPostgresSaver.from_conn_string()`, creating and
tearing down a Postgres connection pool per request
([chat.py:100](apps/api/src/pynote_api/routes/chat.py#L100), [chat.py:160](apps/api/src/pynote_api/routes/chat.py#L160)).
Latency on the hot path + connection churn under load.

**Implementation.**
1. In `apps/api/src/pynote_api/main.py` lifespan (where `setup_checkpoint_tables`
   already runs): enter `AsyncPostgresSaver.from_conn_string(...)` once, compile
   the graph once, stash both on `app.state`.
2. Routes take the compiled graph via a dependency instead of `open_chat_graph()`.
3. Keep `open_chat_graph()` for CLI/eval callers ([eval/prototype/chat.py](eval/prototype/chat.py)).

**Acceptance.** p50 chat TTFB drops by roughly the pool-establishment cost;
no "too many connections" under a 20-concurrent-request smoke test.

---

### 1.4 Prompt caching

**Problem.** No `cache_control` anywhere despite `langchain-anthropic`
supporting it natively (a stated reason for choosing it in PLAN.md). Multi-turn
conversations re-pay the full input price every turn.

**Implementation.** In `node_generate` ([chat_graph.py:127](packages/core/src/pynote_core/chat_graph.py#L127)):
mark the **system prompt** and the **last message of the prior history** with
`{"cache_control": {"type": "ephemeral"}}` so the stable prefix
(system + history) is cached and only the new search results + question are
fresh tokens each turn:

```python
SystemMessage(content=[{"type": "text", "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}}])
```

and set a breakpoint on the final history message before the new
`HumanMessage(content=blocks)`. Search-result blocks come *after* the cache
breakpoints (they change every turn — don't cache them).

**Acceptance.** LangSmith traces show `cache_read_input_tokens > 0` from
turn 2 onward.

---

### 1.5 Post-rerank overlap dedup

**Problem.** 200-char chunk overlap means adjacent chunks both retrieve, both
survive rerank, and near-duplicate text occupies 2 of the 8 `search_result`
slots.

**Implementation.** New pure function in `retrieval.py`, applied after
`rerank()` in `node_retrieve`. Retrieve a couple of spares so dedup doesn't
shrink the packed set:

```python
def dedup_overlaps(hits: list[Hit], *, top_k: int = 8) -> list[Hit]:
    """Drop hits whose char range overlaps a higher-ranked hit from the same part."""
    kept: list[Hit] = []
    for h in hits:  # hits arrive rerank-ordered, best first
        clash = any(
            k.source_part_id == h.source_part_id
            and h.char_start < k.char_end and k.char_start < h.char_end
            for k in kept
        )
        if not clash:
            kept.append(h)
        if len(kept) == top_k:
            break
    return kept
```

Call `rerank(..., top_k=12)` then `dedup_overlaps(top, top_k=8)`.

---

### 1.6 History trimming + slim checkpoints

**Problem.** `add_messages` accumulates forever → per-turn token cost and
latency grow without bound. The checkpointer also snapshots the transient
`hits` field (8 full chunk texts) into **every** checkpoint.

**Implementation.**
1. In `node_generate`, cap what goes to the model with
   `langchain_core.messages.trim_messages` (keep last ~10 messages /
   ~4k tokens, `strategy="last"`, always keep the system message out — it's
   added separately).
2. Clear `hits` at the end of the turn: have `node_map_citations` return
   `{"last_citations": [...], "hits": []}` so the persisted checkpoint doesn't
   carry chunk bodies. (`map_citations` runs after `generate` — the data has
   already been used.)

**Note:** full history remains in checkpoints (needed for the history
endpoint); trimming only bounds the *model input*.

---

## Phase 2 — Persistence & measurement (~1 week)

### 2.1 Per-message citation persistence

**Problem.** `last_citations` is overwritten each turn; reloading a thread
loses citations on all but the final answer
([chat.py:174](apps/api/src/pynote_api/routes/chat.py#L174) hardcodes this).
This undermines the product's core promise.

**Design (recommended: no new table).** Attach citations to the `AIMessage`
itself so the checkpointer persists them naturally:

1. In `node_map_citations`, instead of only returning `last_citations`, emit an
   updated copy of the last AIMessage with
   `additional_kwargs={"citations": [...]}`. With `add_messages`, returning a
   message **with the same `id`** replaces it in state.
2. History endpoint reads `m.additional_kwargs.get("citations", [])` per
   assistant message — delete the `is_last_assistant` special case.
3. Keep `last_citations` for the SSE `citations` event (unchanged wire format).

**Alternative** if you want SQL-queryable citations (analytics, "most-cited
source"): a `message` table written by the API after `done`. More moving parts;
defer until needed.

**Acceptance.** Create a 3-turn thread, reload `/history`: every assistant
message carries its own citations, and clicking one still jumps to the right
span.

---

### 2.2 Retrieval-level eval (recall@k, MRR) ⭐ prerequisite for Phase 3

**Problem.** The ship gate measures end-to-end answers only. When a question
fails you can't tell whether retrieval missed or generation ignored. All the
Phase-3 investments need this to be measurable.

**Design.**
1. Extend the golden JSONL schema:
   ```json
   {"q": "...", "gold_spans": [{"source_title": "...", "page": 4, "must_contain": "exact substring"}]}
   ```
   Substring-based gold labels survive re-chunking (chunk IDs don't).
2. New runner `eval/retrieval_eval.py` that calls `hybrid_retrieve` (k=50) and
   `rerank` directly — **no LLM call** — and scores each stage:
   - `recall@k` for k ∈ {5, 8, 20, 50}: fraction of questions where some
     retrieved chunk contains a gold span (match = `must_contain in chunk.text`
     and page/source agree).
   - `MRR`: reciprocal rank of the first gold-matching chunk.
   - Report three checkpoints: dense-only, hybrid-RRF, post-rerank.
3. Emit JSONL + summary like [eval/run.py](eval/run.py); add a
   `just eval-retrieval` recipe.

**Then use it:** sweep `dense_limit`/`sparse_limit` (currently hardcoded 50/50
at [retrieval.py:102](packages/core/src/pynote_core/retrieval.py#L102)) and
rerank `top_k`. Grow the golden set to 30–50 questions covering: multi-hop,
table lookups, exact-number questions, "not in the docs" negatives, and
multi-turn follow-ups (from 1.1).

---

### 2.3 Parser hygiene (pre-Docling wins)

All in [packages/core/src/pynote_core/parsers/pdf.py](packages/core/src/pynote_core/parsers/pdf.py)
+ a new post-processing step. These change `source_part.text`, so re-parsing
re-runs the whole chain — idempotency already handles that.

1. **Header/footer stripping.** Collect the first/last 1–2 text lines of every
   page; any line (after collapsing digits → `#` to catch page numbers)
   appearing on >60% of pages is boilerplate — drop it from all pages.
2. **De-hyphenation.** Join `(\w)-\n(\w)` when the joined word passes a cheap
   check (appears elsewhere in the doc, or simply always join — low risk in
   English prose).
3. **Cross-page chunk flow.** Today `embed_source` chunks per part, so
   paragraphs spanning pages get truncated at the break. Change
   [tasks.py](apps/worker/src/pynote_worker/tasks.py) `embed_source` to:
   - concatenate part texts with `"\n\n"` into one string, recording each
     part's `(part_id, global_start)`;
   - run `chunk_text` once over the whole document;
   - map each chunk's global offsets back to the *containing* part and
     part-local `char_start/char_end`. Chunks that straddle a boundary: assign
     to the part owning the chunk's midpoint and clamp offsets — **verify the
     citation contract still roundtrips in the test** (`test_chunker.py` has
     the pattern).
   
   ⚠️ This is the fiddliest item in Phase 2. If the offset mapping gets hairy,
   an 80/20 fallback: merge *short* trailing paragraphs into the next page at
   parse time instead, keeping chunking per-part.

**Acceptance.** Re-ingest the eval notebook, retrieval eval (2.2) shows
recall@8 flat-or-up; citation grounding gate stays ≥ 0.90.

---

## Phase 3 — Structural upgrade (1–2 weeks, gated on 2.2)

### 3.1 Structure-aware parsing (Docling)

Already anticipated by PLAN.md and the schema (`level`, `parent_chunk_id`
sit unused). Swap/supplement PyMuPDF with Docling to get:

- section heading hierarchy → store `{"section_path": ["3 Methods", "3.2 Training"]}`
  in `chunk.meta`;
- reading-order fixes for multi-column PDFs;
- table extraction (tables become their own chunks with a serialized-markdown
  body — dramatically better for "what's in table 2" questions).

Keep the `ParsedPart` contract; add optional `headings` metadata to it. The
parser stays behind [parsers/\_\_init\_\_.py](packages/core/src/pynote_core/parsers/__init__.py)'s
`parse(kind, path)` dispatch, so this is additive.

### 3.2 Contextual embeddings (embed enriched, store raw)

The single best-evidenced retrieval upgrade (Anthropic reports ~35–49%
retrieval-failure reduction combined with hybrid search — you already have
hybrid).

**Key insight: the citation contract binds `chunk.text`, not the embedding
input.** So in `embed_source`:

```python
def _context_header(src_title: str | None, meta: dict) -> str:
    path = " > ".join(meta.get("section_path", []))
    return f"{src_title or ''}{' > ' + path if path else ''}".strip()

texts = [f"{_context_header(src.title, chunk_meta)}\n\n{c.text}" for ...]
vectors = await embedder.embed_many(texts)          # enriched → embedding
# ... but persist Chunk(text=c.text, ...) unchanged  # raw → citation contract
```

Also feed the enriched text to the tsvector UPDATE (or add the header terms to
a separate weighted tsvector column with `setweight`) so sparse search benefits
too. Titles are available today; section paths arrive with 3.1 — ship
title-only first if Docling slips.

**Optional stronger variant** (Anthropic's original recipe): one Gemini-Flash
call per chunk generating a 1-sentence "situating context" — better but costs
one cheap-model call per chunk at ingest; measure the header-only version
first.

### 3.3 Embedding model upgrade

Do this **last** in Phase 3 — it requires re-embedding everything and a
migration, so bundle it after 3.1/3.2 rather than re-embedding twice.

- **Choice:** `bge-m3` (local, multilingual, 1024-dim — fastembed supports it,
  the settings enum already lists it) or `voyage-3.5` (API, stronger, costs
  per-token; you already hold a Voyage key for rerank).
- **Migration:** Alembic `ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(1024)`
  (drop + recreate the HNSW index — see
  [20260531_1900_0003_chunks.py](alembic/versions/20260531_1900_0003_chunks.py)),
  bump `embedding_dim`, add the provider branch in
  [embeddings.py](packages/core/src/pynote_core/embeddings.py), re-enqueue
  `embed_source` for every ready source.
- **Sparse language:** `to_tsvector('english', ...)` is hardcoded in
  [tasks.py:264](apps/worker/src/pynote_worker/tasks.py#L264) and the CTE.
  Minimum fix: a `TSVECTOR_CONFIG` setting; better: per-source language
  detection at parse time stored on `source.meta`, `'simple'` config for
  non-English.

**Acceptance.** Retrieval eval before/after on the same golden set; ship only
if recall@8 improves.

---

## Phase 4 — Differentiation (aligns with PLAN.md M8–M15)

| Item | Sketch |
|---|---|
| **4.1 Source-scoped retrieval** | NotebookLM's source toggles. `ChatRequest.source_ids: list[UUID] \| None` → thread through state → `AND source_id = ANY(:sids)` in both CTE legs. UI: checkboxes already implied by `source-list.tsx`. Small, high-visibility. |
| **4.2 Query routing** | Cheap-model classifier ahead of retrieve: `retrieval` / `summary` / `meta`. "Summarize everything" should hit the existing notebook-summary artifact, not top-8 chunks; "what sources do I have" needs no retrieval at all. Extends the `rewrite` node from 1.1 (one call returns both rewrite + route). |
| **4.3 Parent-child retrieval** | With Docling sections (3.1), populate `level=1` section chunks with `parent_chunk_id` links. Retrieve at level 0 (precision), pack the parent section when several siblings hit (context). The schema was built for this. |
| **4.4 Selected-text neighbor retrieval** | `selected_text` currently pollutes the search query ([chat_graph.py:81](packages/core/src/pynote_core/chat_graph.py#L81) — and long selections break `websearch_to_tsquery`, which ANDs terms). Instead: locate the selection's span via substring match against `source_part.text`, pull the chunks covering ±1 neighbor directly by offsets, guarantee them slots in the pack, and retrieve the rest on the rewritten question alone. |
| **4.5 Vision RAG** | PLAN.md M14. Page bbox capture already anticipates it. |

---

## Sequencing summary

```
Week 1   1.1 rewrite → 1.2 bge prefix → 1.3 pool → 1.4 caching → 1.5 dedup → 1.6 trim
Week 2   2.1 per-message citations → 2.2 retrieval eval (+ golden set to 30–50) → 2.3 parser hygiene
Week 3-4 3.1 Docling → 3.2 contextual embeddings → 3.3 embedding upgrade (one re-embed)
Then     4.1 source toggles → 4.2 routing → 4.3 parent-child → 4.4 selection neighbors
```

Definition of done for every retrieval-affecting change, once 2.2 lands:

1. `just eval-retrieval` — recall@8 and MRR not worse.
2. `just eval` (ship gate) — citation grounding ≥ 0.90 holds.
3. Multi-turn golden cases pass.
