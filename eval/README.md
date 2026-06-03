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
