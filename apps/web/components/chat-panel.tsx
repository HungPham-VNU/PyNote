"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { type Citation, type HistoryMessage, getHistory, streamChat } from "@/lib/chat";
import { CitationPill } from "@/components/citation-pill";
import { SourceDrawer, type DrawerTarget } from "@/components/source-drawer";
import { FILL_CHAT_EVENT } from "@/components/suggested-questions";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Msg = {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  pending?: boolean;
};

export function ChatPanel({
  notebookId,
  hasReadySource = true,
}: {
  notebookId: string;
  hasReadySource?: boolean;
}) {
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

  // ---- fill input when a SuggestedQuestion chip is clicked
  useEffect(() => {
    const onFill = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (typeof detail === "string") setInput(detail);
    };
    window.addEventListener(FILL_CHAT_EVENT, onFill);
    return () => window.removeEventListener(FILL_CHAT_EVENT, onFill);
  }, []);

  // ---- restore thread on mount: prefer ?thread= URL param, otherwise pick up
  //      the last thread the user used for THIS notebook (per-browser localStorage).
  useEffect(() => {
    const url = new URL(window.location.href);
    const fromUrl = url.searchParams.get("thread");
    const fromStorage =
      typeof window !== "undefined"
        ? window.localStorage.getItem(`pynote:lastThread:${notebookId}`)
        : null;
    const t = fromUrl ?? fromStorage;
    if (!t) return;

    setThreadId(t);
    // Also reflect the resumed thread in the URL so refresh / share-link still works.
    if (!fromUrl) {
      url.searchParams.set("thread", t);
      window.history.replaceState({}, "", url.toString());
    }
    (async () => {
      try {
        const token = await getToken();
        const { messages: hm } = await getHistory(token, notebookId, t);
        setMessages(hm.map((m: HistoryMessage) => ({ ...m })));
      } catch (e) {
        // If the stored thread no longer exists (e.g. wiped DB), clear it.
        window.localStorage.removeItem(`pynote:lastThread:${notebookId}`);
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
          // Always remember the latest thread we're talking on so navigating
          // away and back picks up where we left off.
          window.localStorage.setItem(
            `pynote:lastThread:${notebookId}`,
            evt.thread_id,
          );
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
    <div className="flex h-full min-h-[440px] flex-col gap-3" data-no-select>
      <div className="flex max-h-[520px] min-h-[260px] flex-1 flex-col overflow-hidden rounded-xl border border-[#424754] bg-[#131314]">
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center py-12 text-center">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#4d8eff]/20 text-[#adc6ff]">
                ✦
              </div>
              <p className="text-sm text-[#e5e2e3]">
                {hasReadySource
                  ? "I'm ready to help you analyze your documents."
                  : "Upload a PDF source to start asking questions."}
              </p>
              {hasReadySource && (
                <p className="mt-1 text-xs text-[#c2c6d6]">
                  Click a suggested chip above, or type your own question below.
                </p>
              )}
            </div>
          )}
          {messages.map((m, i) => (
            <MessageView key={i} msg={m} onCite={openCitation} />
          ))}
          <div ref={scrollEnd} />
        </div>

        {selection && (
          <div className="border-t border-[#fcd34d]/30 bg-[#fcd34d]/10 px-4 py-2 text-xs text-[#fcd34d]">
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
          className="flex gap-2 border-t border-[#424754] bg-[#1c1b1c] p-2.5"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              !hasReadySource
                ? "Add a ready source first…"
                : streaming
                  ? "Streaming…"
                  : "Ask a question about the documents…"
            }
            disabled={streaming || !hasReadySource}
            className="flex-1 rounded-lg border border-[#424754] bg-[#201f20] px-3 py-2 text-sm text-[#e5e2e3] placeholder:text-[#8c909f] focus:border-[#4d8eff] focus:outline-none focus:ring-2 focus:ring-[#4d8eff]/30 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={
              streaming || !hasReadySource || input.trim().length === 0
            }
            className="rounded-lg bg-[#4d8eff] px-4 py-2 text-sm font-semibold text-[#00285d] transition-colors hover:bg-[#adc6ff] disabled:opacity-50"
          >
            ▶
          </button>
        </form>

        {error && (
          <p className="border-t border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-300">
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
    <div
      className={`mb-3 flex items-start gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
          isUser
            ? "bg-[#adc6ff]/20 text-[#adc6ff]"
            : "bg-[#4d8eff]/20 text-[#adc6ff]"
        }`}
        aria-hidden
      >
        {isUser ? "U" : "✦"}
      </div>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed overflow-hidden ${
          isUser
            ? "bg-[#4d8eff] text-[#00285d]"
            : "bg-[#2a2a2b] text-[#e5e2e3]"
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap">
            {msg.content || (msg.pending ? "…" : "")}
          </div>
        ) : (
          <div className="prose prose-sm prose-invert max-w-none break-words">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {msg.content || (msg.pending ? "…" : "")}
            </ReactMarkdown>
          </div>
        )}
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

