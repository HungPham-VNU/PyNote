"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  type NotebookSummary,
  generateNotebookSummary,
  getNotebookSummary,
} from "@/lib/api";

export function SummaryButton({
  notebookId,
  hasReadySource,
}: {
  notebookId: string;
  hasReadySource: boolean;
}) {
  const { getToken } = useAuth();
  const [summary, setSummary] = useState<NotebookSummary | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Try to fetch a cached summary on mount; no error if there isn't one.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        const cached = await getNotebookSummary(token, notebookId);
        if (!cancelled) setSummary(cached);
      } catch {
        // Silent — the GET is best-effort, the button still works.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [notebookId, getToken]);

  const handleGenerate = useCallback(async () => {
    setError(null);
    setGenerating(true);
    try {
      const token = await getToken();
      const fresh = await generateNotebookSummary(token, notebookId);
      setSummary(fresh);
      setDrawerOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  }, [notebookId, getToken]);

  // Esc closes the drawer.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="flex flex-col gap-2" data-no-select>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleGenerate}
          disabled={generating || !hasReadySource}
          className="rounded-xl bg-[#fcd34d] px-4 py-2 text-sm font-semibold text-[#3a2a00] transition-colors hover:bg-[#fde68a] disabled:opacity-50"
          title={
            !hasReadySource
              ? "Add a ready source first"
              : summary
                ? "Re-generate the summary"
                : "Generate a summary"
          }
        >
          {generating
            ? "Summarizing…"
            : summary
              ? "↻ Re-generate"
              : "✦ Generate summary"}
        </button>
        {summary && !generating && (
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="rounded-xl border border-[#424754] bg-[#201f20] px-3 py-2 text-xs text-[#e5e2e3] transition-colors hover:border-[#8c909f] hover:bg-[#2a2a2b]"
          >
            View summary →
          </button>
        )}
        {summary && (
          <span className="text-xs text-[#c2c6d6]">
            Updated {new Date(summary.generated_at).toLocaleString()}
          </span>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}

      {drawerOpen && summary && (
        <SummaryDrawer summary={summary} onClose={() => setDrawerOpen(false)} />
      )}
    </div>
  );
}

function SummaryDrawer({
  summary,
  onClose,
}: {
  summary: NotebookSummary;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-40 flex"
      role="dialog"
      aria-modal="true"
      data-no-select
    >
      <button
        type="button"
        aria-label="Close summary"
        onClick={onClose}
        className="flex-1 bg-black/30 transition-opacity"
      />
      <aside className="flex h-full w-full max-w-[680px] flex-col gap-5 overflow-y-auto bg-[#1c1b1c] p-6 shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-[#424754] pb-4">
          <div className="min-w-0">
            <h2 className="text-[10px] font-semibold uppercase tracking-wider text-[#c2c6d6]">
              Notebook Summary
            </h2>
            <p className="mt-1 text-xl font-semibold leading-snug text-[#e5e2e3]">
              {summary.headline}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[#424754] px-3 py-1 text-xs text-[#e5e2e3] hover:bg-[#2a2a2b]"
          >
            Close
          </button>
        </header>

        <section>
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#c2c6d6]">
            Key Points
          </h3>
          <ul className="space-y-2 text-sm text-[#e5e2e3]">
            {summary.key_points.map((p, i) => (
              <li key={i} className="flex gap-2.5">
                <span
                  aria-hidden
                  className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#4d8eff]"
                />
                <span className="leading-relaxed">{p}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#c2c6d6]">
            Detailed Summary
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-[#e5e2e3]">
            {summary.detailed_summary}
          </p>
        </section>

        <footer className="mt-auto pt-4 text-[10px] text-[#8c909f]">
          Generated {new Date(summary.generated_at).toLocaleString()}
          {summary.model_used ? ` · ${summary.model_used}` : ""}
        </footer>
      </aside>
    </div>
  );
}
