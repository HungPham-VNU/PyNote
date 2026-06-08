/** SSE consumer for the /chat endpoint.
 *
 * Server-Sent Events with EventSource is GET-only; we use POST + a fetch
 * stream reader and parse events ourselves.
 */

export type Citation = {
  cited_text: string;
  search_result_index: number;
  start_char_index: number;
  end_char_index: number;
  chunk_id: string;
  source_id: string;
  source_part_id: string;
  source_title: string | null;
  page: number | null;
  roundtrip_ok: boolean;
};

export type ChatEvent =
  | { type: "start"; thread_id: string }
  | { type: "token"; text: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "done"; thread_id: string; n_citations: number }
  | { type: "error"; message: string };

export type ChatRequest = {
  message: string;
  thread_id?: string;
  selected_text?: string;
};

export type HistoryMessage = {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function* streamChat(
  token: string | null,
  notebookId: string,
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(
    `${API_BASE}/api/v1/notebooks/${notebookId}/chat`,
    {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    },
  );

  if (!res.ok || !res.body) {
    throw new Error(`chat HTTP ${res.status}: ${await res.text()}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE event boundary: a blank line.
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const evt = parseSseBlock(raw);
      if (evt) yield evt;
    }
  }
}

function parseSseBlock(raw: string): ChatEvent | null {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    const payload = JSON.parse(data);
    return { type: event, ...payload } as ChatEvent;
  } catch {
    return null;
  }
}

// ---- history -------------------------------------------------------------

export async function getHistory(
  token: string | null,
  notebookId: string,
  threadId: string,
): Promise<{ thread_id: string; messages: HistoryMessage[] }> {
  const res = await fetch(
    `${API_BASE}/api/v1/notebooks/${notebookId}/threads/${threadId}/history`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: "no-store",
    },
  );
  if (!res.ok) throw new Error(`history HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}
