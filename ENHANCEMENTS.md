# RAG Pipeline Enhancements — Before / After / How to Verify

> Record of the optimization pass implemented on branch `optimize-pipeline`
> (2026-07-07), following [RAG_ROADMAP.md](RAG_ROADMAP.md) Phases 1–2 plus the
> title-only slice of 3.2. For each change: what the system did before, what it
> does now, and how to observe and test it.
>
> **Quick verification of everything at once:**
> ```bash
> just test        # 100 passed, 2 skipped (was 60 before this pass)
> just lint        # clean
> just typecheck   # clean
> ```
> ⚠️ Ingestion-side changes (§7, §8) only affect sources ingested *after* this
> pass — **re-upload or re-enqueue existing sources** to pick them up.

---

## 1. Query rewriting for multi-turn chat (1.1)

**Before.** The `retrieve` node searched on the raw question text. A follow-up
like *"what about the second method?"* embedded and keyword-searched those
literal words, retrieved noise, and the model — instructed to answer only from
search results — replied "the answer isn't in the sources." Multi-turn chat
was effectively broken. `selected_text` (up to 4000 chars) was concatenated
into the search string, which starved the sparse leg: `websearch_to_tsquery`
ANDs terms, so long selections matched nothing. Rerank then used a *different*
query (the bare question) than hybrid search did.

**Now.** A new `rewrite` node runs first in the graph
([chat_graph.py](packages/core/src/pynote_core/chat_graph.py) →
`node_rewrite`). On turn 2+, or when text is selected, one cheap-model call
(Gemini Flash) condenses the last 6 messages + question into a standalone
search query. Hybrid retrieval **and** rerank both use that same query. Turn 1
without a selection skips the call (zero added latency); any model failure
falls back to the raw question, never blocking the turn.

**How to notice.** Ask a question, then follow up with pure pronouns
(*"explain that more simply"*, *"what about the second one?"*). Before: "not
in the sources." Now: a grounded answer with citations.

**How to test.**
- Unit: `uv run pytest packages/core/tests/test_chat_graph.py -q` — asserts
  the `rewrite` node exists in the graph and `search_query` is in the state
  schema.
- Live: `just dev`, ask *"What is this document about?"* then *"Give me more
  detail on the first part"*. In LangSmith, the trace now shows a `rewrite`
  node before `retrieve`; its output `search_query` should read as a
  self-contained query.
- Failure path: unset `GOOGLE_API_KEY` (and use a bad Anthropic key for the
  cheap model) — chat still works, and the worker/API log shows
  `query rewrite failed, falling back to raw question`.

---

## 2. BGE asymmetric query embedding (1.2)

**Before.** `hybrid_retrieve` embedded the query through the same code path as
documents. BGE models are trained asymmetrically — queries need the
instruction prefix *"Represent this sentence for searching relevant
passages:"* — so every dense search ran with a mis-embedded query and quietly
lost recall.

**Now.** `Embedder.embed_query`
([embeddings.py](packages/core/src/pynote_core/embeddings.py)) routes queries
through fastembed's `query_embed`, which applies the BGE prefix. Document
vectors are computed exactly as before — **no re-embedding, no migration**.

**How to notice.** Subtle by nature: dense-leg rankings shift in favor of
semantically relevant chunks. Visible via the retrieval eval (§6) as improved
`dense_recall@k` / `dense_mrr`, and in `/search` results ordering.

**How to test.**
- `uv run python -c "import asyncio; from pynote_core.embeddings import get_embedder; e = get_embedder(); q = asyncio.run(e.embed_query('test')); d = asyncio.run(e.embed_one('test')); print('differs:', q != d)"`
  → `differs: True` proves the query path applies the prefix.
- Stage-level: run the retrieval eval (§6) and compare `dense_*` metrics
  against a run with this commit reverted.

---

## 3. Process-wide checkpointer pool (1.3)

**Before.** Every `/chat` request and every `/history` fetch called
`open_chat_graph()`, which ran `AsyncPostgresSaver.from_conn_string(...)` —
opening a fresh Postgres connection, using it, and tearing it down. That cost
connection setup on the hot path of every request and created connection churn
under concurrency.

**Now.** `open_pooled_chat_graph`
([chat_graph.py](packages/core/src/pynote_core/chat_graph.py)) backs the saver
with a psycopg `AsyncConnectionPool` (max 10, autocommit, dict_row, prepared
statements off for pgbouncer compatibility). The API lifespan
([main.py](apps/api/src/pynote_api/main.py)) enters it once and shares the
compiled graph via `app.state.chat_graph`. Routes use `_graph_for(request)`
([chat.py](apps/api/src/pynote_api/routes/chat.py)), which falls back to the
old per-request path if the pool failed at boot (DB briefly down, tests
without lifespan) — so startup resilience is unchanged.

**How to notice.** Faster time-to-first-token on `/chat` (one connection
handshake removed from the critical path). In Postgres,
`SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE '%psycopg%'`
stays stable under load instead of spiking per request.

**How to test.**
- Live: `just api`, then fire ~20 concurrent chat requests; no
  "too many connections" errors, and `pg_stat_activity` shows a small stable
  pool rather than one connection per in-flight request.
- Degraded boot: start the API with Postgres down — it logs
  `Failed to open the shared chat graph pool; /chat will fall back per-request`
  and still serves once the DB returns.

---

## 4. Anthropic prompt caching (1.4)

**Before.** No `cache_control` anywhere. Every turn of a conversation re-sent
and re-paid the full input: system prompt, entire history, and search results,
at the uncached token rate.

**Now.** `node_generate` places cache breakpoints on (a) the system prompt and
(b) the last *user* turn of prior history (`_with_cache_breakpoint` in
[chat_graph.py](packages/core/src/pynote_core/chat_graph.py)). The stable
prefix — system + history — is written to Anthropic's cache and read back on
subsequent turns at ~10% of input price. Per-turn search results and the new
question come *after* the breakpoints and stay uncached (they change every
turn, caching them would be wasted writes). Human messages were chosen as
breakpoint carriers because they're plain strings; assistant messages carry
citation blocks we don't mutate.

**How to notice.** From turn 2 of any thread, LangSmith traces (or the raw API
response `usage` field) show `cache_read_input_tokens > 0`. Turn 2+ latency to
first token drops. Note: Anthropic only caches prefixes ≥ 1024 tokens (Sonnet),
so very short conversations may show no cache activity — that's expected.

**How to test.**
- Unit: `test_cache_breakpoint_*` in
  [test_chat_graph.py](packages/core/tests/test_chat_graph.py) — wraps string
  content, marks only the last block, never mutates the original message.
- Live: run a 3-turn conversation, open the LangSmith trace for turn 3's
  `generate` call, check `usage.cache_read_input_tokens`.

---

## 5. Rerank over-fetch + overlap dedup (1.5)

**Before.** Chunks are cut with 200-char overlap, so adjacent chunks share
text. Both frequently survived rerank, and near-duplicate passages occupied 2+
of the 8 `search_result` slots sent to Claude — less distinct evidence per
answer.

**Now.** Rerank returns 12 candidates; `dedup_overlaps`
([retrieval.py](packages/core/src/pynote_core/retrieval.py)) walks them
best-first and drops any hit whose `[char_start, char_end)` range overlaps an
already-kept hit from the same `source_part`, then packs 8. Touching ranges
(end == start) are correctly *not* overlaps; identical ranges from different
parts/pages are kept.

**How to notice.** Citations in one answer now reference 8 genuinely distinct
passages; before, you'd occasionally see two citations pointing at
nearly-identical highlighted spans on the same page.

**How to test.**
- Unit: `uv run pytest packages/core/tests/test_retrieval.py -q` — 5 cases
  covering drop, keep-across-parts, top-k, empty, and touching ranges.
- Live: ask a question about a densely relevant page and inspect the SSE
  `citations` event — no two citations from the same `source_part_id` with
  overlapping `start/end_char_index`.

---

## 6. History trimming + slim checkpoints (1.6)

**Before.** Two unbounded-growth problems. (a) The full message history went
to the model every turn — token cost and latency grew linearly with thread
length, forever. (b) The checkpointer snapshotted *all* state every turn,
including the transient `hits` field — 8 full chunk texts written into every
checkpoint row, bloating the `checkpoints` tables.

**Now.** (a) `_trim_history` caps model input at a 12-message tail, aligned to
start on a user turn (a window starting mid-turn confuses the model and breaks
cache-prefix stability). Full history is still checkpointed — the history
endpoint needs it — only *model input* is bounded. (b) `node_map_citations`
returns `hits: []`, so the end-of-turn checkpoint no longer carries chunk
bodies.

**How to notice.** Long threads stop getting slower/more expensive per turn.
Checkpoint storage growth per turn drops sharply:

```sql
SELECT pg_size_pretty(pg_total_relation_size('checkpoint_blobs'));
-- watch growth per chat turn, before vs after
```

**How to test.**
- Unit: `test_trim_history_*` in
  [test_chat_graph.py](packages/core/tests/test_chat_graph.py) — passthrough
  under the cap, Human-alignment above it.
- Live: run a 10+ turn thread; the LangSmith trace of the last `generate` call
  shows ≤ 12 history messages in the prompt, while `GET .../history` still
  returns all turns.

---

## 7. Per-message citation persistence (2.1)

**Before.** Citations lived only in the transient `last_citations` state
field, overwritten every turn. The history endpoint hardcoded citations onto
the *final* assistant message only — reloading a thread stripped citations
from every earlier answer, killing the product's core promise (click any
citation → jump to source).

**Now.** `node_map_citations` copies the resolved citations onto the
answering `AIMessage.additional_kwargs["citations"]` and re-emits the message
— `add_messages` replaces by message id, so the checkpointed history carries
citations per message permanently. The history endpoint
([chat.py](apps/api/src/pynote_api/routes/chat.py)) reads them per message,
with a `last_citations` fallback for the final turn of threads persisted
before this change (old threads don't regress). The SSE wire format is
unchanged.

**How to notice.** Have a 3-turn conversation, reload the page (or hit
`GET /api/v1/notebooks/{nb}/threads/{tid}/history`): **every** assistant
message now includes its `citations` array, and clicking a citation on an old
turn still highlights the right span.

**How to test.**
- Live API check:
  ```bash
  curl -s -H "X-Dev-User: u1" -H "X-Dev-Org: o1" \
    localhost:8000/api/v1/notebooks/$NB/threads/$TID/history \
    | python -c "import json,sys; ms=json.load(sys.stdin)['messages']; print([len(m['citations']) for m in ms if m['role']=='assistant'])"
  ```
  → non-zero counts on all cited turns, not just the last.

---

## 8. Retrieval-stage eval — recall@k / MRR (2.2)

**Before.** The only eval was end-to-end ([eval/run.py](eval/run.py)): when a
question scored badly you couldn't tell whether retrieval missed the passage
or generation ignored it. Retrieval knobs (`dense_limit`/`sparse_limit`/
`top_k`, hardcoded 50/50/8) had never been tuned against evidence.

**Now.** [eval/retrieval_eval.py](eval/retrieval_eval.py) scores retrieval
alone — **no LLM calls, free to run** — at four stages: `dense` (pgvector
only), `sparse` (tsvector only), `hybrid` (RRF fusion), and `packed`
(post-rerank + dedup: the top-8 the model actually sees). Metrics:
recall@{5,8,20,50} and MRR per stage. Gold labels are substrings
(`must_contain`), so they survive re-chunking; chunk IDs would not.

**How to use.**
```bash
cp eval/golden/retrieval.template.jsonl eval/golden/retrieval.jsonl
# label it: questions + exact substrings from an ingested notebook
just eval-retrieval NOTEBOOK_UUID
```
Output: per-question JSONL + a `_summary` row; stderr prints
`dense: r@8=… mrr=…  sparse: …  hybrid: …  packed: …`. Reading it: if `hybrid`
recall is high but `packed` is low, the reranker is discarding gold; if
`dense` is low but `sparse` high (or vice versa), one leg is misconfigured.

**How to test.** `uv run pytest eval/tests/test_retrieval_eval.py -q` —
matching normalization, page/title filters, 1-based MRR ranks, per-leg
ordering, summary averaging.

**⚠️ Open task:** the golden set must be hand-labeled against a real notebook
before this produces numbers. It is the gate for all Phase-3 work.

---

## 9. PDF parser hygiene (2.3 — partial)

**Before.** Raw PyMuPDF text per page. Running headers, footers, and page
numbers appeared in every chunk — embedded into vectors, indexed into
tsvector, wasting rerank attention and polluting citations. Words hyphenated
across line breaks (`improve-\nment`) were stored split and invisible to
keyword search.

**Now** ([pdf.py](packages/core/src/pynote_core/parsers/pdf.py)):
- **Header/footer stripping** — the first/last 2 non-empty lines of each page
  are candidates; after digit-folding (`Page 3` ≡ `Page 7`), any line
  appearing on >60% of pages (min 3) is dropped, *only* from page edges so
  body text that coincidentally matches survives. A guard keeps a page's
  original text if stripping would empty it.
- **De-hyphenation** — `(?<=\w)-\n(?=[a-z])` joins wrapped words; the
  lowercase-continuation requirement avoids gluing list items (`-\nAlpha`).

Cleaning happens at parse time, so stored `source_part.text` is clean and the
citation contract binds the cleaned text.
**Deliberately not done:** cross-page chunk flow — with page-based parts it
cannot preserve `part.text[start:end] == chunk.text`; it resolves properly
when Docling section parts land (roadmap 3.1).

**How to notice.** After re-ingesting a paginated PDF, chunk texts
(`SELECT text FROM chunk WHERE source_id='…' LIMIT 5`) no longer start/end
with the document's running header or `Page N`; searching a word that was
hyphen-split in the PDF now finds it.

**How to test.**
- Unit: `uv run pytest packages/core/tests/test_pdf_parser.py -q` — 7 tests:
  headers/page numbers stripped, unique edge lines survive, hyphen wraps
  joined, list dashes untouched.
- Live: re-upload a real PDF with headers, then compare chunk texts before /
  after in psql.

---

## 10. Contextual embeddings, title-only (3.2-lite)

**Before.** A chunk from page 40 embedded as an orphan window of text with no
document identity — "the results show a 12% improvement" couldn't be found by
"what were the results in the Smith paper?". `tsv` was built from chunk text
only.

**Now** ([tasks.py](apps/worker/src/pynote_worker/tasks.py) `embed_source`):
the source **title** is prepended to the text fed to the embedder
(`"{title}\n\n{chunk}"`), and `setweight`-ed into the tsvector at weight `B`
(body stays `A`, so body matches outrank title-only matches). **Stored
`chunk.text` is untouched** — the citation contract binds stored text, not
embedding input, so citations still roundtrip exactly. Section paths join the
header when Docling lands.

**How to notice.** Queries naming a document ("in the annual report, what…")
rank that source's chunks higher in `/search` and chat retrieval — for sources
ingested after this change.

**How to test.**
- Contract safety: `just test` — the chunker/citation roundtrip tests still
  pass because stored text is unchanged.
- Live: re-ingest a source, then
  ```sql
  SELECT tsv FROM chunk WHERE source_id = '…' LIMIT 1;
  ```
  → title lexemes appear with `:…B` weight markers. Then query `/search` with
  a title keyword + body term and confirm that source's chunks lead.

---

## Verification status at hand-off

| Layer | Status |
|---|---|
| Unit/integration suite | ✅ 100 passed, 2 skipped (API-key smoke tests) |
| Ruff lint + format | ✅ clean |
| Mypy (`packages/core/src`) | ✅ clean |
| Live SSE chat loop against real DB + Anthropic key | ⬜ not yet run — do one manual pass (§1, §4, §7 checks) |
| M7 ship gate (`eval/run.py`) after re-ingest | ⬜ re-run to confirm citation grounding ≥ 0.90 |
| Retrieval golden set labeled | ⬜ required before Phase 3 |
