# PyNote — Plan to NotebookLM Parity

> A staged plan from greenfield to NotebookLM-class application.
> Author: Plan generated 2026-05-27. Update the **status** column as you ship.

---

## 0. Locked-in decisions

> **Provider / pricing**: see [COSTS.md](COSTS.md). For the university-project free-tier configuration, providers in the table below are swapped (e.g., Claude via GitHub Models, Gemini for cheap ops, BGE-M3 local embeddings) but the architecture is unchanged.

| Area | Choice | Rationale |
|---|---|---|
| Deployment | Multi-user cloud-deployable web service | User-chosen |
| Models | API-first: Claude (Sonnet 4.6 / Haiku 4.5 / Opus 4.7), Voyage (`voyage-3-large`, `rerank-2.5`), ElevenLabs v3 | Quality > local cost savings for v1 |
| Auth | Clerk (orgs + RBAC) | OOTB tenancy |
| Hosting | Portable Docker (`docker-compose` + per-service Dockerfiles + Procfile) | Fly / Railway / Render / ECS all viable later |
| DB | Postgres 16 + pgvector + pg_trgm | One store for metadata + vectors + sparse |
| Object store | S3-compatible (R2 in prod, MinIO in dev) | No egress fees, presigned uploads |
| Workers | arq (Redis) | Async-native, simpler than Celery |
| Orchestration | **LangGraph** for LLM workflows, **arq** for ingest jobs | LangGraph for stateful multi-step LLM; arq for deterministic queues |
| LLM SDK | `langchain-anthropic` (`ChatAnthropic`) — uses Citations API + prompt caching natively | Verified via Context7 |
| Retrieval | `EnsembleRetriever`(PGVector dense + custom Tsvector sparse) → `ContextualCompressionRetriever` + `VoyageAIRerank` | Standard LC composition |
| Observability | LangSmith | Auto-instruments every Runnable + graph node |
| API | FastAPI (async), SSE for streaming | |
| Frontend | Next.js 15 (App Router) + React 19 + Tailwind + shadcn/ui + react-pdf | Need DOM control for citation highlight |
| v1 scope | Grounded chat with inline citations only | User-chosen; ship narrow, expand later |

### Where LangChain is intentionally kept out
- **Parsing**: Docling directly (LC loaders lose layout/table fidelity).
- **Chunking**: custom hierarchical chunker (LC splitters don't guarantee char-offset preservation we need for citation roundtrip).
- **Ingest queues**: arq directly (LangGraph is for LLM flows, not generic jobs).

---

## 1. Reference architecture

```
                   Browser (Next.js 15)
                          │
                  Clerk-protected /api
                          │
                ┌─────────▼─────────┐
                │   FastAPI         │   SSE token streams
                │   (async)         │
                └─┬───────────────┬─┘
                  │               │
       enqueue    │               │  invoke
       (arq)      │               │  (LangGraph)
                  ▼               ▼
        ┌─────────────────┐  ┌─────────────────────────┐
        │ arq workers     │  │ LangGraph runtime       │
        │ - parse_source  │  │ - chat_graph            │
        │ - embed_chunks  │  │ - artifact_graph (v2)   │
        │ - asr_audio     │  │ - audio_overview (v3)   │
        │ - outline_src   │  │  PostgresSaver state    │
        └─┬─────────┬─────┘  └──────────┬──────────────┘
          │         │                   │
          ▼         ▼                   ▼
        R2/S3   Postgres 16 + pgvector + pg_trgm
       (files)   (metadata + chunks + vectors + tsvector + graph state)
                          │
                       Redis (arq queue)
                          │
                      LangSmith (traces)
```

---

## 2. NotebookLM feature → milestone matrix

| NotebookLM feature | Delivered in | Notes |
|---|---|---|
| Notebook = scoped workspace | M0–M1 | `notebook` table, Clerk org scoping |
| Upload PDF | M1 | |
| Grounded chat w/ inline citations | M3–M5 | The v1 core |
| Click citation → jump to source span | M5 | The "wow" moment |
| Suggested questions | M6 | Generated at ingest |
| Multi-PDF in one notebook | M2+ | Falls out of the data model |
| DOCX upload | M8 | |
| Web URL ingestion | M8 | |
| YouTube ingestion | M8 | Native transcript w/ ASR fallback |
| Audio upload (ASR) | M8 | |
| Image upload (VLM caption) | M8 | |
| Notes as durable artifacts | M9 | |
| Save chat answer as note | M9 | |
| Notes feed back into index | M9 | |
| Auto-summary of source / notebook | M10–M11 | |
| FAQ generation | M11 | |
| Study guide | M11 | |
| Briefing doc | M11 | |
| Timeline | M11 | |
| Mind map | M12 | React Flow |
| Audio Overview (two-host podcast) | M13 | ElevenLabs v3 dialogue |
| Vision-grounded RAG (figures/tables) | M14 | voyage-multimodal-3 + ColPali-style |
| Sharing (public read-only) | M15 | |
| Comments / collaboration | M15 | |

---

## 3. Phased roadmap

### Effort key
- **XS** ≤ 1 day · **S** 1–2 days · **M** 3–5 days · **L** 1–2 weeks · **XL** 2+ weeks
- Estimates are solo focused dev days. Real wall time depends on you.

---

## Phase 0 — Foundation

### M0 · Repo + dev environment + auth — **M**

**Goal:** A new dev can `git clone` and `docker compose up` and see a Clerk-protected dashboard talk to a Clerk-protected FastAPI.

**Tasks**
1. Initialize monorepo: `apps/api`, `apps/web`, `apps/worker`, `packages/core` (shared Python), `packages/shared-types` (OpenAPI → TS), `infra/`, `eval/`.
2. `pyproject.toml` (uv or poetry) with dependency groups: `api`, `worker`, `core`, `dev`, `eval`.
3. `docker-compose.dev.yml` services: `postgres` (with `pgvector`, `pg_trgm` extensions), `redis`, `minio` (R2-compatible local), `mailhog`, `langsmith-proxy` optional.
4. Postgres init script: `CREATE EXTENSION pgvector; CREATE EXTENSION pg_trgm;`.
5. Alembic set up; first migration creates `org`, `user`, `membership`, `notebook` tables with FK from app to Clerk `org_id` (TEXT, not FK to local users — Clerk owns identity).
6. FastAPI skeleton: `/healthz`, Clerk JWT middleware (verify `azp`, `org_id`, `sub`), dependency injection for `current_user` and `current_org`.
7. Next.js 15 skeleton with Clerk `<ClerkProvider>` + `<OrganizationSwitcher>`. Server-side fetch from `/api/notebooks` proves auth flow.
8. arq worker skeleton with `noop_task` and a `/jobs/{id}` status endpoint.
9. LangSmith env wiring; smoke test: a trivial `ChatAnthropic.invoke("ping")` shows up in LangSmith.
10. `Procfile` and `Dockerfile.{api,worker,web}` for portable hosting.
11. `.env.example`, README quickstart, pre-commit (ruff, mypy, prettier, eslint), GitHub Actions CI (lint + unit tests).

**Acceptance**
- [ ] `docker compose up` produces a working stack.
- [ ] Logged-in user can create a notebook via `POST /notebooks` and see it in the web UI.
- [ ] A no-op arq job enqueues and completes; appears in `job` table.
- [ ] One LangSmith trace visible from a `ChatAnthropic` call.

**Risks**
- Clerk JWT verification details — write integration test against a Clerk dev instance early.

---

## Phase 1 — Ingestion

### M1 · Single-PDF ingestion (no chunking yet) — **M**

**Goal:** Upload a PDF, see it parse into pages with extracted text and figure captions.

**Tasks**
1. Add tables: `source`, `source_part` (per Plan §5 / `PLAN.md` data model).
2. R2/S3 client (boto3) with **presigned PUT** endpoint: `POST /notebooks/{id}/sources/presign` returns URL + `source_id`.
3. Browser uploads directly to R2; calls `POST /sources/{id}/finalize` to mark uploaded.
4. arq job `parse_source(source_id)`:
   a. Download bytes from R2 to tmpdir.
   b. Detect kind via magic bytes + extension (PDF only this milestone).
   c. Docling parse → for each page emit `source_part(ordinal, page, text, bbox_jsonb)`.
   d. For pages containing figures/tables: Sonnet 4.6 vision call captioning each figure → append caption text to `part.text` with a separator marker preserved.
   e. Mark `source.status = parsed`.
5. Next.js: drag-and-drop uploader, source list with status pills, page preview.

**Acceptance**
- [ ] A 50-page PDF uploads in <10s, parses in <90s.
- [ ] `source_part` rows exist for every page with non-empty `text` for text pages, captions appended for figure pages.
- [ ] UI shows status transitions: `pending → uploading → parsing → parsed`.

**Risks**
- Docling memory on large PDFs — set a worker memory limit + chunk pages if > 200.

---

### M2 · Hierarchical chunking + embedding + tsvector — **M**

**Goal:** Sources become searchable: dense + sparse indexes populated, query endpoint returns top-K with scores.

**Tasks**
1. Add `chunk` table with `embedding vector(1024)`, `tsv tsvector`, `parent_chunk_id`.
2. Implement `HierarchicalChunker` in `packages/core`:
   - Level 1 (section): split on Docling-detected headings; if missing, fall back to ~1500-token windows.
   - Level 0 (fine): **300-token windows with 50-token overlap inside each L1.** (Reference checkpoint — `rag_skill` uses 1000/200 word for prose chatbots; ours are tighter because reranker is doing the heavy lifting. Revisit in M3 tuning.)
   - Both levels persist `(char_start, char_end)` against `source_part.text` (post-caption-append). **This is the citation contract — write a property test.**
   - Chunk metadata persisted as `chunk.meta_jsonb`: `{source_title, page, section_path, ordinal_in_section}` so retrieved hits carry display info without joins.
3. arq job `embed_source(source_id)`:
   - Batch L0 chunks 128 at a time to `voyage-3-large`.
   - Populate `embedding`.
   - Populate `tsv` via `to_tsvector('english', text)` in SQL.
   - Mark `source.status = ready`.
4. Indexes:
   ```sql
   CREATE INDEX ON chunk USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
   CREATE INDEX ON chunk USING gin (tsv);
   CREATE INDEX ON chunk (source_id, level);
   ```
5. `POST /notebooks/{id}/search?q=...` returns top-K with `{score_dense, score_sparse, score_rrf}`.

**Acceptance**
- [ ] Property test: round-tripping `text[chunk.char_start:chunk.char_end]` against the original `source_part.text` matches `chunk.text` exactly for 1000 random chunks.
- [ ] `/search` returns sensible top-10 on a known query in <500ms for a 1000-chunk notebook.

**Risks**
- Heading detection failure → bad L1 boundaries. Mitigate with a fallback test corpus.

---

## Phase 2 — Core RAG v1 → 🚀 SHIP v1

### M3 · Retrieval + Citations API prototype (standalone) — **S**

**Goal:** **De-risk the citation contract before building UI.** A 200-LOC Python script proves end-to-end Citations API roundtrip works on a real PDF.

**Tasks**
1. `eval/prototype/retrieval_citations.py`:
   - Load one ingested notebook from local DB.
   - Build `EnsembleRetriever([PGVector dense, TsvectorRetriever sparse], weights=[0.6, 0.4])`.
   - Wrap with `ContextualCompressionRetriever(VoyageAIRerank(model="rerank-2.5", top_k=8))`.
   - Pack top-8 as Anthropic `search_result` content blocks (one per chunk).
   - Call `ChatAnthropic(model="claude-sonnet-4-6")` with `citations.enabled=True`.
   - Parse response: assert every text block with a citation maps `(search_result_index, start_char_index, end_char_index)` back to a known chunk and a substring of `chunk.text`.
2. **Adopt the 5-case smoke shape** as the prototype's test matrix — same five cases re-used in M7's golden harness:
   1. **Health** — every provider (Postgres, Voyage, Anthropic, optional Gemini fallback) reachable.
   2. **Basic Q** — single-turn grounded question, cites at least one source.
   3. **Context-aware follow-up** — second turn references the first; citation may switch sources.
   4. **Selection-context** — caller passes `selected_text` from a source span ("explain this"); answer demonstrably grounds in or near it.
   5. **Session persistence** — re-load the same thread, verify history and citations round-trip from `PostgresSaver`.
3. Run against 5 representative PDFs (academic, legal, technical, narrative, marketing). Hand-grade 10 questions each.
4. Tune: top-K (try 6/8/12), reranker `top_k`, ensemble weights. Record results in `eval/notes/m3-tuning.md`.

**Acceptance**
- [ ] All 5 smoke cases pass on the prototype.
- [ ] On 50 questions across 5 PDFs, ≥ 90% of citations resolve to a valid chunk substring.
- [ ] Citation map handles edge cases: multi-sentence citations, no-citation answers, refusals.
- [ ] Tuning notes capture chosen hyperparameters for M4.

**Risks**
- This is the biggest unknown. If citation fidelity is <90% even after tuning, reconsider passing whole `document` blocks instead of `search_result` blocks for relevant sources.

---

### M4 · Chat end-to-end (LangGraph + SSE) — **L**

**Goal:** Web chat works against a real notebook, citations appear as pills, no UI highlight yet.

**Tasks**
1. Implement `chat_graph` per architecture sketch in M3 plan:
   - Nodes: `classify` (Haiku) → `rewrite` (Haiku) → `retrieve` → `pack` → `generate` (Sonnet, streaming) → `map_citations`.
   - State persisted via `PostgresSaver` (reuses our Postgres).
2. `POST /notebooks/{id}/chat` accepts `{thread_id, message, selected_text?}`.
   - When `selected_text` is present, prepend it to the rewrite node's prompt: *"User has selected this passage from a source: «…». Their question: …"*. The pack node prioritizes the source containing the selection (boost its RRF score).
   - Streams via SSE using `chat_graph.astream(stream_mode="messages")`.
3. Map citations: for each returned `char_location` citation, look up the originating chunk → resolve to `(source_id, source_part_id, char_start, char_end)`. Persist on `message.citations_jsonb`.
4. **`GET /notebooks/{id}/threads/{thread_id}/history`** — returns ordered messages with citations. Reads from `PostgresSaver`'s thread state (single source of truth — don't dual-write a `message` table).
5. Next.js chat panel:
   - Streaming markdown renderer (`react-markdown` + custom citation pill component).
   - **Selection-context banner**: when the user selects text inside the source viewer, show a yellow "Use as context for next question" chip; sending the message attaches the selection to the request and clears it.
6. Empty/error states: source not ready, no chunks, retrieval timeout, model error.

**Acceptance**
- [ ] User asks a question; tokens stream; citation pills appear inline; clicking a pill shows the cited text in a side panel (no PDF jump yet).
- [ ] Selecting text in the source viewer surfaces the selection banner; the next answer is demonstrably scoped toward that selection.
- [ ] `GET /threads/{id}/history` returns the same messages the UI shows after a reload.
- [ ] LangSmith shows the full graph trace per turn (including `selected_text` in the rewrite span).

**Risks**
- Citation map fragility — covered by M3 hardening.
- Streaming + state checkpoint interactions — write an integration test.
- Selection-context can over-bias retrieval; cap the boost so out-of-selection sources still surface when relevant.

---

### M5 · PDF viewer + citation jump — **M**

**Goal:** The NotebookLM moment: click pill → PDF opens at the page, span highlighted.

**Tasks**
1. `react-pdf` viewer component in a slide-over panel.
2. Custom highlight layer: overlays positioned by mapping `(source_part_id, char_start, char_end)` to bounding rects via the text layer.
   - At ingest time, persist per-chunk text-layer rect data (from Docling bbox) on `chunk.meta_jsonb` to avoid recomputing in the browser.
3. URL state: `?source=...&page=...&highlight=charA-charB` makes jumps shareable.
4. Multi-source citations in one answer: pill cycles through them in the panel.

**Acceptance**
- [ ] Clicking any citation pill opens the source at the correct page within 500ms.
- [ ] Highlight rectangle covers the cited span (visual QA on 20 citations).
- [ ] Works for non-PDF sources too: for now, web pages show as an iframe with text fragment, audio shows with timestamp jump.

**Risks**
- PDF text-layer coordinates drift on some PDFs — use Docling bbox + char-range mapping as ground truth; fall back to "open page, no highlight" if mapping fails (don't show wrong highlight).

---

### M6 · Suggested questions + notebook home polish — **S**

**Goal:** Notebook page feels alive: source list, suggested questions, recent threads.

**Tasks**
1. At end of `embed_source` worker, enqueue `outline_source(source_id)`:
   - Haiku 4.5 over L1 chunks → returns `{abstract, key_entities, suggested_questions[3..5]}` (structured output).
   - Persist on `source.meta_jsonb`.
2. Notebook home: source cards with abstract; aggregate "Try asking…" chip row.
3. Empty notebook onboarding state.

**Acceptance**
- [ ] First chat session for a new notebook has ≥3 useful suggested questions.

**Risks** — low.

---

### M7 · Eval harness, settings, v1 polish → 🚀 **SHIP v1** — **M**

**Goal:** Ship-quality. Telemetry and an automated quality gate before announcing v1.

**Tasks**
1. Golden set: 30 question/answer pairs across 5 representative notebooks, hand-graded.
2. Eval pipeline (`eval/run.py`):
   - Ragas: `context_precision`, `context_recall`, `faithfulness`, `answer_relevancy`.
   - Custom metric: **citation-grounding** = fraction of answer sentences with a citation whose `cited_text` is a substring of source.
   - Stored in `eval/results/<run_id>.jsonl`; LangSmith experiment per run.
3. CI: nightly eval on golden set; alert if any metric drops > 5%.
4. Settings page: notebook deletion (cascade), source removal, model selection (Sonnet default, Opus toggle), citation density slider, language.
5. Error states for every failure path; user-facing copy.
6. Pricing/usage scaffolding (per-org token counters; not enforced yet).
7. Cookie banner + privacy + ToS placeholders.
8. Landing page.

**Acceptance / Ship gates**
- [ ] All Ragas metrics ≥ 0.85 on golden set.
- [ ] Citation grounding ≥ 0.92.
- [ ] p95 first-token latency < 3s on a 1000-chunk notebook.
- [ ] Zero unhandled-error paths in instrumentation (Sentry/LangSmith clean for a week).
- [ ] One external user can complete: sign up → create notebook → upload PDF → ask 3 questions → click citations → understand it works.

🚀 **SHIP v1.** Stop, get user feedback, decide whether to continue.

---

## Phase 3 — Source breadth

### M8 · Multi-source ingestion — **L**

**Goal:** All NotebookLM source types ingestable.

Each loader is a `SourceLoader` plugin returning `list[SourcePart]`. Add per-kind:
1. **DOCX** — `python-docx` + Docling DOCX → paragraphs as parts. ~1 day.
2. **Web URL** — `trafilatura` for main-content extraction; fall back to `playwright` for JS-heavy pages. Capture title, byline, publish_date in metadata. ~2 days.
3. **YouTube** — `yt-dlp` to get video metadata + native captions (multiple languages). If captions missing, download audio → route to ASR pipeline. Parts = caption segments with timestamps. ~1 day (+ASR).
4. **Audio (mp3/m4a/wav)** — `faster-whisper` (large-v3) in a separate worker queue (GPU-optional). Parts = utterances with `(start_sec, end_sec, speaker?)`. Diarization optional (pyannote). ~2 days.
5. **Image** — Sonnet 4.6 vision: caption + OCR text → single part. ~0.5 day.

**Citation UX per kind:**
- Audio: pill jumps to timestamp in audio player.
- Video: pill jumps to YouTube embed at timestamp.
- Web: pill opens iframe with text fragment hash `#:~:text=...`.
- DOCX: pill opens a rendered HTML view (Docling → HTML).

**Acceptance**
- [ ] All 6 source types (PDF + 5 new) ingest cleanly on a representative sample.
- [ ] Mixed-source notebooks return answers citing across types.
- [ ] Citation jumps work per kind.

**Risks**
- YouTube ToS — only handle user-supplied URLs; don't pre-fetch popular content.
- Audio diarization quality varies; ship without it, add as toggle.

---

### M9 · Notes as first-class sources — **S**

**Goal:** Users can take notes, save model output as notes, and notes become searchable just like uploaded sources.

**Tasks**
1. `note` table + CRUD endpoints; markdown body.
2. Rich-text editor (TipTap) embedded in the notebook UI.
3. "Save answer as note" button on assistant messages; pre-fills with answer + citations.
4. On note save, enqueue `parse_source` with `kind='note'` (uses markdown → text path, no chunking changes needed).
5. Re-index on note edit (debounced).

**Acceptance**
- [ ] A note saved from an answer can be retrieved as a citation in a later question.
- [ ] Edits to notes update the index within 30s.

---

## Phase 4 — Artifacts → 🚀 SHIP v2

### M10 · Artifact framework — **M**

**Goal:** A generic, versioned, regeneratable artifact system that all subsequent artifact types plug into.

**Tasks**
1. `artifact` table: `(id, notebook_id, kind, body_jsonb, version, status, model_used, prompt_hash, created_at)`.
2. `artifact_graph` (LangGraph): generic `select_sources → outline → expand → assemble → validate`.
3. `POST /notebooks/{id}/artifacts` enqueues generation; `GET /artifacts/{id}` polls; SSE for streaming.
4. UI: artifact list per notebook, per-artifact viewer with "regenerate" + version history.
5. Cost gate: each artifact shows estimated tokens; user confirms before running expensive ones.

**Acceptance**
- [ ] One artifact type (`summary`) works end-to-end: generated, viewable, regenerateable, versioned.

---

### M11 · Study artifacts (summary, FAQ, study guide, briefing doc, timeline) — **L**

**Goal:** Five artifact templates plugged into the framework.

Each template is: Pydantic output schema + system prompt + post-processor. Ship in order of value:

1. **Summary** (already in M10 as canary) — Opus 4.7, long-context with cached notebook context.
2. **FAQ** — structured `[{question, answer, citations[]}]`. Use search_result blocks so each answer is grounded.
3. **Study guide** — `{learning_objectives[], key_concepts[], practice_questions[], glossary{term: definition}}`.
4. **Briefing doc** — newsletter-style narrative with sections + pull quotes + citations.
5. **Timeline** — entity/event extraction; render as horizontal timeline in UI (already structured for v3 mind map reuse).

**Acceptance**
- [ ] All 5 generate on a complex multi-source notebook in <90s each.
- [ ] Every claim in every artifact has a citation.

---

### M12 · Mind map → 🚀 **SHIP v2** — **M**

**Goal:** Visual graph of concepts and relationships, interactive.

**Tasks**
1. Generation: Opus 4.7 structured output `{nodes[{id,label,kind,citations[]}], edges[{from,to,label}]}`.
2. Two-pass: first pass extracts entities + concepts; second pass extracts relationships (better than asking for both at once).
3. Render with **React Flow**; deterministic layout via `elkjs` (hierarchical) or `dagre`.
4. Node click → side panel showing source excerpts; edge click → showing relationship evidence.
5. Export PNG/SVG.

**Acceptance**
- [ ] A 20-source academic notebook produces a navigable map with <100 nodes, <300 edges, layout converges <2s.
- [ ] Every node has at least one citation.

🚀 **SHIP v2.** Artifacts marketed as the headline new capability.

---

## Phase 5 — Audio Overview → 🚀 SHIP v3

### M13 · Audio Overview (two-host podcast) — **L**

**Goal:** Click a button, get a 5–15 min two-host conversational audio overview with chapter markers and a synced transcript.

**Tasks**
1. **Script generation** (`audio_overview_graph` in LangGraph):
   - Outline pass (Opus 4.7) → structured `{chapters: [{title, key_beats[], source_refs[]}]}`.
   - Dialogue pass per chapter (Opus 4.7) → structured `[{speaker: A|B, text, emotion?, prosody_hint?}]`.
   - Linter pass: enforces speaker alternation, no over-long monologues, casual register.
2. **TTS**: ElevenLabs v3 multi-voice. Two pre-selected voices (configurable). Per-line TTS with prosody hints; cache by `hash(voice, text)`.
3. **Assembly**: `pydub` to concatenate clips with light crossfade; chapter markers as ID3v2.4 frames.
4. **Storage**: mp3 in R2; transcript JSON in artifact `body_jsonb` with `(speaker, text, start_ms, end_ms, citations[])`.
5. **Player**: custom audio component with waveform, speaker labels, click-to-jump on transcript lines, citation pills.
6. **Cost guardrail**: estimated cost before generation; org-level monthly cap.

**Acceptance**
- [ ] A 10-source notebook produces a 10-minute audio in <8 min wall time.
- [ ] Transcript synced within 200ms of audio across the full duration.
- [ ] Citations attached to ≥80% of factual statements in the transcript.

**Risks**
- TTS cost. Cache aggressively; throttle per org.
- Two-voice dialogue prosody — script linter is essential.

🚀 **SHIP v3.** This is the marquee feature.

---

## Phase 6 — Multimodal & scale

### M14 · Vision-grounded RAG (figures, tables, charts) — **L**

**Goal:** Questions about figures, charts, and tables get accurate answers grounded in image content, not just OCR.

**Tasks**
1. Add `voyage-multimodal-3` path: for each PDF page that contains a figure/table, also embed the **rendered page image** as a separate "page-image chunk."
2. Retrieval: weighted ensemble across text chunks + page-image chunks (separate vector column or separate table).
3. Generation: when a page-image chunk is in top-K, attach the page image as an `image` content block to Claude (Sonnet 4.6 vision); cite via `search_result` referencing the page.
4. UI: citation jump to a page can highlight the figure bbox if cited.

**Acceptance**
- [ ] On a chart-heavy PDF (e.g. economic report), questions about chart values are answered correctly ≥80% of the time and cite the page.

**Risks**
- Storage cost for page images. Compress to webp, downscale to 1536px long edge.

---

### M15 · Sharing + light collaboration — **M**

**Goal:** Read-only public links, in-org sharing, comments on artifacts.

**Tasks**
1. `share_link` table: `(notebook_id, token, scope: read_chat|read_artifacts|read_all, expires_at)`.
2. Public viewer route: no Clerk needed, scoped read-only.
3. Org-internal sharing via Clerk org membership.
4. Comment threads on artifacts (mind map nodes, audio overview chapters, individual chat messages).
5. Activity log per notebook.

**Acceptance**
- [ ] Share link works in incognito, denies write attempts, expires correctly.
- [ ] Org members see shared notebooks in a "Shared with me" view.

---

## Phase 7 — Enterprise readiness → 🚀 SHIP v4

### M16 · Tenancy hardening, audit, quotas — **L**

**Goal:** Sellable to organizations with security/IT review.

**Tasks**
1. **Postgres RLS** turned on with policy per `org_id`. Switch app role to RLS-enforced role. Defense-in-depth over app-layer scoping.
2. Audit log: every state-changing API call → `audit_event` (actor, org, action, target, before/after hash).
3. Quotas: per-org caps on sources/notebook, total bytes, monthly token budget; enforcement middleware.
4. SSO via Clerk (SAML / Google Workspace).
5. Data residency option: per-org R2 bucket region.
6. Background job: re-index after model upgrade (migrations for embedding model changes — see Cross-Cutting §4).
7. Backup + restore runbook (Postgres logical backups + R2 lifecycle).
8. Status page + incident response playbook.

**Acceptance**
- [ ] External pen-test report with no critical or high findings.
- [ ] RLS test suite: every cross-org query attempt returns empty.

---

### M17 · BYOK + on-prem option → 🚀 **SHIP v4** — **XL**

**Goal:** Enterprise dealbreaker check-box: bring-your-own-key for Anthropic/Voyage/ElevenLabs, and a self-hosted distribution.

**Tasks**
1. Per-org credentials vault (Postgres + envelope encryption via KMS). UI to enter & validate keys.
2. Route LLM/embedding/rerank/TTS calls through per-org clients when BYOK set; fall back to platform keys.
3. Cost reporting separation: platform-billed vs BYOK-billed.
4. Helm chart for Kubernetes deploy (api + worker + postgres + redis as a values-driven chart).
5. On-prem licensing + telemetry opt-out.
6. SOC 2 Type I controls implemented (access reviews, change management, encryption-in-transit/at-rest, vendor management).

🚀 **SHIP v4** — NotebookLM-parity feature surface + enterprise readiness.

---

## 4. Cross-cutting concerns

### 4.1 Security & tenancy
- Every table with tenant data has `org_id` (TEXT, Clerk org id) or links to a row that does.
- App-layer scoping by default; Postgres RLS in M16.
- All R2 keys prefixed with `org/<org_id>/notebook/<notebook_id>/source/<source_id>/...`; presigned URLs scoped per-object, never per-prefix.
- Clerk JWT verified on every request; `org_id` from JWT, never from the request body.
- LLM prompt-injection guardrails: never include user content in system blocks; cite always from `search_result` blocks; refuse tool calls in v1.

### 4.2 Cost monitoring
- LangSmith trace metadata includes `org_id`, `notebook_id`, `kind`.
- Nightly job aggregates token usage per org from LangSmith export → `usage_daily` table.
- Org dashboard shows usage; M16 adds enforcement.

### 4.3 Embedding-model migration strategy
You **will** want to change embedding models someday. Plan for it:
- `chunk.embedding_model TEXT NOT NULL` column from day one.
- Migration runner: dual-write to new column, reindex per-notebook in background, swap pointer atomically.
- Never block users on migration; allow per-notebook reindex priority.

### 4.4 Testing strategy
- **Unit**: pure functions (chunker offsets, citation mapping) — pytest.
- **Integration**: full ingest + retrieve against a containerized Postgres — pytest with `testcontainers`.
- **E2E**: Playwright on the web app, 3 critical paths (signup→upload→ask, citation jump, regenerate artifact).
- **Eval**: Ragas + custom metrics on golden set; nightly in CI from M7.
- **Property**: chunk offset roundtrip (M2), citation map (M3).
- **Load**: k6 on `/chat` at 10/50/200 concurrent — required before M16.

### 4.5 CI/CD
- GitHub Actions: lint + unit on PR; integration on merge to `main`; eval nightly; container build + push on tag.
- Migrations gated by manual approval in prod.
- LangSmith linked from PRs: each PR can link a "before/after eval run" comparison.

### 4.6 Observability
- LangSmith for LLM traces.
- OpenTelemetry → otel-collector for FastAPI/arq spans; ship to Tempo/Honeycomb.
- Sentry for unhandled errors (client + server).
- Postgres slow-query log on; pg_stat_statements enabled.

### 4.7 Data privacy
- Per-org delete API; hard-deletes within 30 days from request (R2 lifecycle + Postgres cascade).
- No source content in LangSmith traces by default (redaction filter); enable per-org for debugging only with consent.

---

## 5. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Citation char-offsets drift on weird PDFs | High | High | M3 prototype + property tests; bbox fallback |
| R2 | Anthropic rate limits at scale | Medium | High | Token bucket per org; queue + retry on 429; cache aggressively |
| R3 | ElevenLabs cost runaway on Audio Overview | High | High | Per-org caps; estimate + confirm UX; line-level cache |
| R4 | pgvector HNSW recall degrades > 1M chunks | Medium | Medium | Plan for partitioned indexes per notebook; consider Qdrant migration past 5M chunks |
| R5 | YouTube/web parsing breaks on site changes | High | Low | Loader version pinning; per-source fallback to ASR/screenshot |
| R6 | Clerk vendor lock | Low | Medium | Keep all `org_id`/`user_id` as opaque strings; auth boundary thin |
| R7 | LangChain breaking API changes | Medium | Medium | Pin minor versions; integration tests on upgrade |
| R8 | Long-running graph state grows unbounded | Medium | Low | TTL on `checkpoints` table; nightly vacuum |

---

## 6. What I'd do differently than NotebookLM

- **Sources are first-class objects with stable URIs** (`notebook://{nid}/source/{sid}`) — citations are real links, deep-linkable from emails/Slack.
- **Every artifact is regeneratable and versioned.** NotebookLM's artifacts can feel one-shot.
- **BYOK from M17.** A meaningful enterprise differentiator.
- **Open data export** (markdown + JSON archive) at any time — anti-lock-in.

---

## 7. Open follow-ups (not blocking M0)

These can be deferred but should be decided before the relevant milestone:

| Decision | Needed by | Default |
|---|---|---|
| LangSmith Cloud vs self-host | M0 | Cloud free tier for v1; self-host at M16 |
| Sentry vs Better Stack vs none | M0 | Sentry |
| ElevenLabs voice selection (creator account vs API-only) | M13 | API-only, 2 fixed voices, custom voices unlocked at M15 |
| RDS Postgres vs managed Postgres on Fly/Railway | M16 | Whatever the chosen host offers |
| Pricing model | Before public launch | Tiered: free (1 notebook, 50MB sources, 100 chats/mo) / pro ($20/mo, 50 notebooks, 5GB, 5k chats, audio overview) / team ($40/seat) / enterprise |

---

## 8. How to use this plan

1. **Linearly** through Phase 0–2 (M0–M7). Do not parallelize before v1.
2. **Stop at v1**, run on real users for ≥2 weeks, then choose next phase based on demand.
3. Phases 3 and 4 can interleave; M8 loaders can be added one-per-week alongside artifact work.
4. **Always keep the eval green.** Any change to ingest, retrieval, or generation runs the golden set in CI before merge.
5. Update each milestone's **status** column below as you ship.

| # | Milestone | Effort | Status | Notes |
|---|---|---|---|---|
| M0 | Foundation | M | ☐ | |
| M1 | Single-PDF ingest | M | ☐ | |
| M2 | Chunking + embedding | M | ☐ | |
| M3 | Retrieval/Citations prototype | S | ☐ | De-risk gate |
| M4 | Chat end-to-end | L | ☐ | |
| M5 | PDF viewer + citation jump | M | ☐ | |
| M6 | Suggested questions | S | ☐ | |
| M7 | Eval + polish → ship v1 | M | ☐ | 🚀 v1 |
| M8 | Multi-source ingestion | L | ☐ | |
| M9 | Notes as sources | S | ☐ | |
| M10 | Artifact framework | M | ☐ | |
| M11 | Study artifacts | L | ☐ | |
| M12 | Mind map → ship v2 | M | ☐ | 🚀 v2 |
| M13 | Audio overview → ship v3 | L | ☐ | 🚀 v3 |
| M14 | Vision RAG | L | ☐ | |
| M15 | Sharing | M | ☐ | |
| M16 | Tenancy hardening | L | ☐ | |
| M17 | BYOK + on-prem → ship v4 | XL | ☐ | 🚀 v4 |

**Estimated total**: 14–22 focused-dev-weeks solo to M17.
**v1 alone**: 3–5 weeks.
**v1 → v3 (NotebookLM feature parity)**: 10–14 weeks.
