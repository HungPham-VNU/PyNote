"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { type Citation, type HistoryMessage, getHistory, streamChat } from "@/lib/chat";
import { CitationPill } from "@/components/citation-pill";
import { SourceDrawer, type DrawerTarget } from "@/components/source-drawer";

type Msg = {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  pending?: boolean;
};

export function ChatPanel({ notebookId }: { notebookId: string }) {
  const { getToken } = useAuth();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [selection, setSelection] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<DrawerTarget | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollEnd = useRef<HTMLDivElement | null>(null);

  const openCitation = useCallback((c: Citation) => {
    setDrawer({
      sourceId: c.source_id,
      sourceTitle: c.source_title,
      page: c.page,
      citedText: c.cited_text,
    });
  }, []);

  // ---- selection capture: any text selected on the page becomes available
  // as context. The PDF viewer in M5 will be the primary source — for now,
  // selecting text anywhere on the notebook page qualifies.
  useEffect(() => {
    const onSelect = () => {
      const text = window.getSelection()?.toString().trim() ?? "";
      // Ignore selections inside our own controls.
      const node = window.getSelection()?.anchorNode?.parentElement;
      if (node?.closest("[data-no-select]")) return;
      if (text.length > 10) setSelection(text);
    };
    document.addEventListener("mouseup", onSelect);
    return () => document.removeEventListener("mouseup", onSelect);
  }, []);

  // ---- restore thread on mount if one is in the URL
  useEffect(() => {
    const url = new URL(window.location.href);
    const t = url.searchParams.get("thread");
    if (!t) return;
    setThreadId(t);
    (async () => {
      try {
        const token = await getToken();
        const { messages: hm } = await getHistory(token, notebookId, t);
        setMessages(hm.map((m: HistoryMessage) => ({ ...m })));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [notebookId, getToken]);

  // ---- auto-scroll to the latest message
  useEffect(() => {
    scrollEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const send = useCallback(async () => {
    const message = input.trim();
    if (!message || streaming) return;

    setError(null);
    setInput("");
    const pendingSelection = selection;
    setSelection(null);

    setMessages((cur) => [
      ...cur,
      { role: "user", content: message, citations: [] },
      { role: "assistant", content: "", citations: [], pending: true },
    ]);
    setStreaming(true);

    abortRef.current = new AbortController();
    try {
      const token = await getToken();
      const stream = streamChat(
        token,
        notebookId,
        {
          message,
          thread_id: threadId ?? undefined,
          selected_text: pendingSelection ?? undefined,
        },
        abortRef.current.signal,
      );
      for await (const evt of stream) {
        if (evt.type === "start") {
          if (!threadId) {
            setThreadId(evt.thread_id);
            const url = new URL(window.location.href);
            url.searchParams.set("thread", evt.thread_id);
            window.history.replaceState({}, "", url.toString());
          }
        } else if (evt.type === "token") {
          setMessages((cur) => {
            const next = [...cur];
            const last = next[next.length - 1];
            if (last && last.role === "assistant") {
              next[next.length - 1] = {
                ...last,
                content: last.content + evt.text,
              };
            }
            return next;
          });
        } else if (evt.type === "citations") {
          setMessages((cur) => {
            const next = [...cur];
            const last = next[next.length - 1];
            if (last && last.role === "assistant") {
              next[next.length - 1] = { ...last, citations: evt.citations };
            }
            return next;
          });
        } else if (evt.type === "done") {
          setMessages((cur) => {
            const next = [...cur];
            const last = next[next.length - 1];
            if (last && last.role === "assistant") {
              next[next.length - 1] = { ...last, pending: false };
            }
            return next;
          });
        } else if (evt.type === "error") {
          setError(evt.message);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [input, selection, streaming, notebookId, threadId, getToken]);

  return (
    <div className="flex flex-col gap-3" data-no-select>
      <div className="rounded-md border border-neutral-200 bg-white">
        <div className="max-h-[480px] min-h-[200px] overflow-y-auto px-4 py-3">
          {messages.length === 0 && (
            <p className="py-8 text-center text-sm text-neutral-500">
              Ask a question about your sources.
            </p>
          )}
          {messages.map((m, i) => (
            <MessageView key={i} msg={m} onCite={openCitation} />
          ))}
          <div ref={scrollEnd} />
        </div>

        {selection && (
          <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
            <span className="font-medium">Use as context:</span>{" "}
            <span className="italic">
              {selection.length > 160 ? selection.slice(0, 160) + "…" : selection}
            </span>
            <button
              type="button"
              onClick={() => setSelection(null)}
              className="ml-2 underline"
            >
              clear
            </button>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="flex gap-2 border-t border-neutral-200 p-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              streaming ? "Streaming…" : "Ask anything about your sources"
            }
            disabled={streaming}
            className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400 disabled:bg-neutral-100"
          />
          <button
            type="submit"
            disabled={streaming || input.trim().length === 0}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
          >
            Send
          </button>
        </form>

        {error && (
          <p className="border-t border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">
            {error}
          </p>
        )}
      </div>

      <SourceDrawer target={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}

function MessageView({
  msg,
  onCite,
}: {
  msg: Msg;
  onCite: (c: Citation) => void;
}) {
  const isUser = msg.role === "user";
  return (
    <div className={`mb-3 ${isUser ? "text-right" : "text-left"}`}>
      <div
        className={`inline-block max-w-[90%] whitespace-pre-wrap rounded-md px-3 py-2 text-sm ${
          isUser ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-900"
        }`}
      >
        {msg.content || (msg.pending ? "…" : "")}
        {msg.citations.length > 0 && (
          <span className="ml-1">
            {msg.citations.map((c, i) => (
              <CitationPill key={i} citation={c} index={i} onClick={onCite} />
            ))}
          </span>
        )}
      </div>
    </div>
  );
}

