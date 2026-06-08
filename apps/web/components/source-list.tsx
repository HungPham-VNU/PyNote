"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { deleteSource, listSources, type Source } from "@/lib/api";
import { StatusPill } from "@/components/status-pill";

const TERMINAL = new Set(["parsed", "ready", "failed"]);
const POLL_MS = 2500;

export function SourceList({
  notebookId,
  initial,
}: {
  notebookId: string;
  initial: Source[];
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [sources, setSources] = useState<Source[]>(initial);

  // Re-sync when the server-rendered `initial` changes — e.g. after the
  // uploader calls router.refresh(). Comparing by id+status keeps this from
  // firing on every parent re-render.
  const initialKey = initial.map((s) => `${s.id}:${s.status}`).join("|");
  useEffect(() => {
    setSources(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialKey]);

  // Poll while anything is in flight. Stops automatically once all sources are terminal.
  useEffect(() => {
    const anyInFlight = sources.some((s) => !TERMINAL.has(s.status));
    if (!anyInFlight) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const token = await getToken();
        const next = await listSources(token, notebookId);
        if (!cancelled) setSources(next);
      } catch {
        // soft fail — next tick will retry
      }
    };
    const handle = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [sources, notebookId, getToken]);

  const onDelete = useCallback(
    async (id: string) => {
      const token = await getToken();
      await deleteSource(token, id);
      setSources((cur) => cur.filter((s) => s.id !== id));
      router.refresh();
    },
    [getToken, router],
  );

  if (sources.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-[#424754] px-4 py-5 text-center text-xs text-[#c2c6d6]">
        No sources yet. Upload a PDF above.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-1.5">
      {sources.map((s) => (
        <li
          key={s.id}
          className="rounded-xl border border-[#424754] bg-[#201f20] p-3 transition-colors hover:border-[#8c909f]"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 flex-1 items-start gap-2">
              <span
                aria-hidden
                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#4d8eff]/15 text-xs text-[#adc6ff]"
              >
                📄
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-[#e5e2e3]">
                  {s.title}
                </p>
                <div className="mt-1 flex items-center gap-1.5">
                  <StatusPill status={s.status} />
                  {s.byte_size && (
                    <span className="text-[10px] text-[#c2c6d6]">
                      {(s.byte_size / 1024 / 1024).toFixed(1)} MB
                    </span>
                  )}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onDelete(s.id)}
              aria-label="Delete source"
              className="ml-1 rounded-md p-1 text-[10px] text-[#c2c6d6] transition-colors hover:bg-[#2a2a2b] hover:text-red-400"
            >
              ✕
            </button>
          </div>
          {s.error && (
            <p className="mt-2 text-[10px] text-red-400" title={s.error}>
              {s.error}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
