# eval — golden sets and the M3 prototype

The M3 milestone exists to de-risk **one** thing before we build the chat UI:
do Anthropic's Citations API char-locations actually round-trip back to the
chunks we retrieved? If yes, M4's chat graph is just plumbing. If no, we tune
retrieval before sinking days into the app shell.

## Layout

```
eval/
├── prototype/         # the M3 CLI + helpers
│   ├── retrieval.py   # hybrid SQL + Voyage rerank
│   ├── citations.py   # pack search_result blocks + parse + validate
│   ├── chat.py        # one-shot retrieve→rerank→generate
│   └── m3.py          # CLI (5 smoke subcommands + bulk grader)
├── golden/            # JSONL question files for bulk runs
│   └── sample.jsonl
├── fixtures/          # PDFs / artifacts checked in for repeatable runs
└── results/           # generated JSONL outputs (gitignored)
```

## Prerequisites

Before running M3 you need a notebook with at least one source ingested past M2
(`status='ready'`, chunks embedded). Verify in psql:

```sql
SELECT s.id, s.title, s.status, COUNT(c.id) chunks
FROM source s LEFT JOIN chunk c ON c.source_id = s.id
GROUP BY s.id ORDER BY s.created_at DESC LIMIT 5;
```

Provider keys needed:

| Var | Why | Free path |
|---|---|---|
| `ANTHROPIC_API_KEY` | Calls Claude with citations enabled | GitHub PAT via GH Models (no Anthropic account needed) |
| `VOYAGE_API_KEY` | Optional — Voyage rerank-2.5 | 200M tok/mo free at voyageai.com |

If `VOYAGE_API_KEY` is unset, the prototype skips reranking and uses the first 8 RRF hits as-is — fine for early sanity checks.

## The 5 smoke subcommands

```bash
NB="paste your notebook uuid here"

# 0. Health — Anthropic + Voyage + Postgres + chunk count
uv run python -m eval.prototype.m3 health

# 1. ask — one grounded question. Inspect the citation fidelity %
uv run python -m eval.prototype.m3 ask --notebook $NB --q "What does the document conclude?"

# 2. chat — three-turn follow-up. Last turn must still cite cleanly.
uv run python -m eval.prototype.m3 chat --notebook $NB \
  --turns "What is the main topic?" "Why does that matter?" "How is it measured?"

# 3. select — user selected a span; the question is about it.
uv run python -m eval.prototype.m3 select --notebook $NB \
  --selection "the paragraph the user highlighted" \
  --q "Explain this in plain terms."

# 4. stability — same query 3x, top hits identical?
uv run python -m eval.prototype.m3 stability --notebook $NB --q "Your question" --runs 3
```

Each subcommand exits 0 on success, non-zero on the failure condition listed in
its `--help`. Useful in CI later.

## Bulk grading — the M3 acceptance gate

PLAN.md M3 asks for ≥ 90% citation roundtrip on 50 questions across 5 PDFs.

```bash
uv run python -m eval.prototype.m3 bulk \
  --notebook $NB --file eval/golden/sample.jsonl \
  > eval/results/run-$(date +%Y%m%d-%H%M%S).jsonl
```

The output is JSONL — one record per question plus a final `_summary` line
with `avg_fidelity` and a `passed` boolean. Grep the summary:

```bash
jq 'select(._summary == true)' eval/results/run-*.jsonl
```

## Tuning record

Keep a short note per tuning iteration in `eval/notes/m3-tuning.md` (one block
per run, what you changed, what avg_fidelity moved to). The numbers below `0.9`
are signal — usually:

- **Low fidelity, high citation count** → Claude is over-citing; tighten the system prompt or drop `top_k`.
- **Low fidelity, low citation count** → retrieval missed the answer source; raise `candidate_k`, check the rerank.
- **No citations at all** → forgot `citations.enabled=True` on the search_result blocks (don't — it's hard-coded in `pack_search_results`).

---

## M7 ship-gate eval (`eval/run.py`)

M3 proves the citation contract holds for one query. **M7 turns that into a
gate**: a JSONL of questions, three lite metrics (citation_grounding,
faithfulness_lite, answer_relevancy_lite) with fixed thresholds, and an
optional Ragas pass for semantic-grade verdicts.

### Run the lite gate (fast, $0)

```bash
uv run python -m eval.run \
  --notebook $NB \
  --file eval/golden/sample.jsonl \
  > eval/results/m7-$(date +%Y%m%d-%H%M%S).jsonl
```

Stdout is one JSONL row per question + a trailing `_summary`. Stderr shows
progress and the final verdict line:

```
GATE: PASS  cg=94%  fl=71%  ar=38%
```

Gate thresholds (from `eval/metrics.py`):
- `citation_grounding ≥ 0.90` — fraction of citations whose char-offsets
  round-trip to the chunk text.
- `faithfulness_lite ≥ 0.60` — answer tokens overlap with retrieved contexts.
- `answer_relevancy_lite ≥ 0.25` — answer tokens overlap with the question.

The lite metrics are crude (word-overlap, no LLM). They're a sanity floor —
the **citation_grounding** number is the one that actually matters, because
it's deterministic and char-exact.

### Add Ragas for semantic scoring (slow, costs judge tokens)

```bash
# One-time: install the eval dep group
uv sync --all-packages --group eval

# Then add the flag
uv run python -m eval.run \
  --notebook $NB \
  --file eval/golden/sample.jsonl \
  --with-ragas \
  > eval/results/m7-ragas-$(date +%Y%m%d-%H%M%S).jsonl
```

Each row gets a `"ragas": {...}` block with four scores. Setup is wired for
free tier:

- **Judge LLM**: `get_cheap_model()` (Gemini Flash). One call per metric per
  row — ~4-12 calls per question depending on which metrics apply.
- **Embeddings**: local BGE-small via `_BGEEmbeddingsForRagas` (in
  `eval/ragas_metrics.py`). Needed for `answer_relevancy`; without it Ragas
  silently falls back to OpenAIEmbeddings and dies if `OPENAI_API_KEY` is
  unset.

### Metric semantics — what each number tells you

| Metric | Failure pattern caught |
|---|---|
| `citation_grounding` | "Citation says it's at offset X but it isn't" — drift, hallucinated quotes |
| `Ragas faithfulness` | "Answer says claim C but C isn't in any retrieved chunk" — semantic hallucination |
| `Ragas answer_relevancy` | "Answer doesn't address the question" — off-topic responses |
| `Ragas context_precision` | "Top-K has chunks that aren't relevant to the question" — bad retrieval |
| `Ragas context_recall` | "The chunks miss information from the reference answer" — under-retrieved |

`context_precision` and `context_recall` both need a `reference` field on
each question (the expected answer). The current `golden/sample.jsonl` has
no references, so those two stay `None` unless you enrich the file:

```jsonl
{"q": "What is the main topic?", "reference": "...the expected answer..."}
```

### When to run which

| Loop | Use | Why |
|---|---|---|
| Tuning `top_k` / RRF weights | Lite metrics (no `--with-ragas`) | Free, deterministic, <1s/question |
| Pre-PR sanity check | Lite metrics | Same as above, runs in CI |
| Pre-ship / nightly | `--with-ragas` | Catches semantic regressions the lite metrics can't |
| Debugging one bad row | Lite metrics + open the row in `eval/results/*.jsonl` | `ungrounded` field lists citations that failed roundtrip |

### Pinned dep note

`pyproject.toml` pins `langchain-community<0.4` in the `eval` group. Ragas
0.4.3 still imports `langchain_community.chat_models.vertexai`, which moved
to its own package in lc-community 0.4.0. Remove the pin when ragas itself
ships a fix.
