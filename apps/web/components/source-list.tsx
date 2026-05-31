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
      <p className="rounded-md border border-dashed border-neutral-300 px-4 py-6 text-center text-sm text-neutral-500">
        No sources yet. Upload a PDF above.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-neutral-200 rounded-md border border-neutral-200 bg-white">
      {sources.map((s) => (
        <li
          key={s.id}
          className="flex items-center justify-between gap-4 px-4 py-3 text-sm"
        >
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate font-medium">{s.title}</span>
              <StatusPill status={s.status} />
            </div>
            {s.error && (
              <p className="mt-1 text-xs text-red-600" title={s.error}>
                {s.error}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => onDelete(s.id)}
            className="text-xs text-neutral-500 hover:text-red-600"
          >
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}
