# PyNote — Mermaid Diagrams

Diagrams for the RAG teach-in presentation. GitHub renders these natively;
in VS Code use the built-in Markdown preview (with Mermaid support) or paste
into <https://mermaid.live> to export SVG/PNG at any size.

Each diagram carries an `init` block matching the deck's Control Room palette
(`#0B1119` background, `#5EEAC3` teal, `#FFB04C` amber) so exported images
drop into the slides without restyling.

---

## 1. Use case diagram

Mermaid has no native use-case type; this is the conventional flowchart
approximation — actors outside the system boundary, use cases inside.

```mermaid
%%{init: {'theme':'base','themeVariables':{
  'primaryColor':'#101927','primaryTextColor':'#DCE7EE','primaryBorderColor':'#5EEAC3',
  'lineColor':'#7E93A3','clusterBkg':'#0B1119','clusterBorder':'#3A4A5A',
  'fontFamily':'IBM Plex Mono','fontSize':'15px'}}}%%
flowchart LR
    researcher(["👤 Researcher"])
    admin(["👤 Org Admin"])
    worker(["⚙️ Background Worker"])

    subgraph pynote["PyNote — RAG notebook"]
        uc_upload(["Upload PDF source"])
        uc_ask(["Ask a question — streaming chat"])
        uc_cite(["Click citation → exact span in PDF"])
        uc_search(["Search notebook — hybrid"])
        uc_chips(["Pick a suggested question"])
        uc_summary(["View notebook summary"])
        uc_manage(["Manage notebooks & org members"])
        uc_ingest(["Parse · chunk · embed source"])
        uc_outline(["Build outline & mind map"])
    end

    researcher --> uc_upload
    researcher --> uc_ask
    researcher --> uc_cite
    researcher --> uc_search
    researcher --> uc_chips
    researcher --> uc_summary
    admin --> uc_manage

    uc_upload -. triggers .-> uc_ingest
    uc_ingest -. then .-> uc_outline
    uc_ask -. includes .-> uc_search
    worker --> uc_ingest
    worker --> uc_outline

    style uc_cite stroke:#FFB04C
    style uc_ask stroke:#FFB04C
```

---

## 2. Architecture diagram

```mermaid
%%{init: {'theme':'base','themeVariables':{
  'primaryColor':'#101927','primaryTextColor':'#DCE7EE','primaryBorderColor':'#5EEAC3',
  'lineColor':'#7E93A3','clusterBkg':'#0B1119','clusterBorder':'#3A4A5A',
  'fontFamily':'IBM Plex Mono','fontSize':'15px'}}}%%
flowchart TB
    subgraph client["Client"]
        web["apps/web — Next.js 15
        Clerk auth · react-pdf viewer · dark M3 theme"]
    end

    subgraph backend["Backend"]
        api["apps/api — FastAPI
        notebooks · sources · chat SSE · search · summary"]
        chatgraph["LangGraph chat_graph
        rewrite → retrieve → generate → map_citations"]
        workerp["apps/worker — arq
        parse_source → embed_source → outline_source"]
    end

    subgraph data["Data layer"]
        pg[("Postgres 16
        pgvector HNSW · tsvector GIN · LangGraph checkpoints")]
        redis[("Redis
        arq job queue")]
        blob[("MinIO / R2
        raw PDF bytes")]
    end

    subgraph providers["External providers"]
        claude["Anthropic Claude — Citations API"]
        voyage["Voyage rerank-2.5 · optional"]
        gemini["Gemini Flash — outline / summary"]
        langsmith["LangSmith traces · optional"]
    end

    web -- "Clerk JWT · SSE /api/v1/*" --> api
    api --> chatgraph
    api -- enqueue --> redis
    redis --> workerp
    workerp -- parts · chunks · vectors --> pg
    workerp -- download PDF --> blob
    chatgraph -- "hybrid RRF · checkpoints" --> pg
    chatgraph -- "search_result blocks" --> claude
    chatgraph -. rerank top-50 .-> voyage
    workerp -. outline .-> gemini
    chatgraph -. auto-trace .-> langsmith

    style claude stroke:#FFB04C
    style pg stroke:#FFB04C
```

---

## 3. Chat query flow (sequence)

```mermaid
%%{init: {'theme':'base','themeVariables':{
  'primaryColor':'#101927','primaryTextColor':'#DCE7EE','primaryBorderColor':'#5EEAC3',
  'lineColor':'#7E93A3','actorBkg':'#101927','actorBorder':'#5EEAC3','actorTextColor':'#DCE7EE',
  'signalColor':'#7E93A3','signalTextColor':'#9FB2C0','noteBkgColor':'#1A2230','noteTextColor':'#DCE7EE','noteBorderColor':'#FFB04C',
  'fontFamily':'IBM Plex Mono','fontSize':'14px'}}}%%
sequenceDiagram
    actor U as Researcher
    participant W as Web (Next.js)
    participant A as API (FastAPI)
    participant G as LangGraph
    participant P as Postgres
    participant C as Claude

    U->>W: ask question
    W->>A: POST /chat — SSE opens
    A->>G: astream(state, thread_id)
    G->>G: rewrite — follow-up → standalone query
    G->>P: hybrid RRF (dense + sparse), top 50
    P-->>G: candidates
    G->>G: rerank → 12 · dedup → pack 8
    G->>C: search_result blocks + question
    C-->>A: token stream
    A-->>W: SSE tokens (live)
    C-->>G: citations — char offsets
    G->>G: map_citations — roundtrip verify
    G->>P: checkpoint thread state
    A-->>W: citations event
    W-->>U: answer + clickable citations
```

---

## 4. Ingestion pipeline (flow)

```mermaid
%%{init: {'theme':'base','themeVariables':{
  'primaryColor':'#101927','primaryTextColor':'#DCE7EE','primaryBorderColor':'#5EEAC3',
  'lineColor':'#7E93A3','clusterBkg':'#0B1119','clusterBorder':'#3A4A5A',
  'fontFamily':'IBM Plex Mono','fontSize':'15px'}}}%%
flowchart LR
    pdf[/"PDF upload"/] --> parse["parse_source
    PyMuPDF · strip boilerplate
    de-hyphenate · detect headings"]
    parse --> parts[("source_part
    clean text + heading offsets")]
    parts --> chunker["structure-aware chunker
    paragraphs pack → sentences split
    headings = hard cuts"]
    chunker --> embed["embed_source
    BGE-small 384-d · fastembed
    header: title › section path"]
    embed --> chunks[("chunk table
    HNSW dense · GIN sparse
    meta.section_path")]
    chunks --> outline["outline_source
    suggested-question chips"]

    style chunker stroke:#FFB04C
    style embed stroke:#FFB04C
```
