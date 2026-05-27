"use client";

import { useState, useTransition } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { createNotebook } from "@/lib/api";

export function CreateNotebookForm() {
  const { getToken } = useAuth();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        startTransition(async () => {
          try {
            const token = await getToken();
            await createNotebook(token, title);
            setTitle("");
            router.refresh();
          } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
          }
        });
      }}
      className="flex gap-2"
    >
      <input
        type="text"
        required
        minLength={1}
        maxLength={255}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Notebook title"
        className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
      />
      <button
        type="submit"
        disabled={pending || title.length === 0}
        className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
      >
        {pending ? "Creating…" : "New notebook"}
      </button>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
