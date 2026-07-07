"use client";

import { useState, useTransition } from "react";
import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { deleteNotebook, updateNotebook, type Notebook } from "@/lib/api";

export function NotebookCard({ notebook }: { notebook: Notebook }) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(notebook.title);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const rename = () => {
    const next = title.trim();
    if (next.length === 0 || next === notebook.title) {
      setTitle(notebook.title);
      setEditing(false);
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const token = await getToken();
        await updateNotebook(token, notebook.id, next);
        setEditing(false);
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Rename failed");
      }
    });
  };

  const remove = () => {
    if (!window.confirm(`Delete notebook “${notebook.title}”? This removes all its sources and chats.`)) {
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const token = await getToken();
        await deleteNotebook(token, notebook.id);
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Delete failed");
      }
    });
  };

  return (
    <li className="group rounded-2xl border border-[#424754] bg-[#1c1b1c] transition-colors hover:border-[#4d8eff] hover:bg-[#201f20]">
      <div className="flex items-start gap-3 p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#4d8eff]/20 text-[#adc6ff]">
          📓
        </div>
        <div className="min-w-0 flex-1">
          {editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                rename();
              }}
            >
              <input
                autoFocus
                type="text"
                required
                minLength={1}
                maxLength={255}
                value={title}
                disabled={pending}
                onChange={(e) => setTitle(e.target.value)}
                onBlur={rename}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setTitle(notebook.title);
                    setEditing(false);
                  }
                }}
                className="w-full rounded-lg border border-[#4d8eff] bg-[#201f20] px-2 py-1 text-sm font-semibold text-[#e5e2e3] focus:outline-none focus:ring-2 focus:ring-[#4d8eff]/30"
              />
            </form>
          ) : (
            <Link href={`/notebook/${notebook.id}`} className="block">
              <p className="truncate text-sm font-semibold text-[#e5e2e3]">
                {notebook.title}
              </p>
              <p className="mt-1 text-xs text-[#c2c6d6]">Open notebook →</p>
            </Link>
          )}
          {error && (
            <p className="mt-1 text-xs text-red-400" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <button
            type="button"
            title="Rename notebook"
            aria-label="Rename notebook"
            disabled={pending}
            onClick={() => setEditing(true)}
            className="rounded-lg p-1.5 text-[#c2c6d6] hover:bg-[#4d8eff]/20 hover:text-[#adc6ff] disabled:opacity-50"
          >
            ✏️
          </button>
          <button
            type="button"
            title="Delete notebook"
            aria-label="Delete notebook"
            disabled={pending}
            onClick={remove}
            className="rounded-lg p-1.5 text-[#c2c6d6] hover:bg-red-500/20 hover:text-red-400 disabled:opacity-50"
          >
            🗑️
          </button>
        </div>
      </div>
    </li>
  );
}
