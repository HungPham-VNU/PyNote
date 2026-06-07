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
        placeholder="New notebook title…"
        className="flex-1 rounded-xl border border-[#424754] bg-[#201f20] px-4 py-2.5 text-sm text-[#e5e2e3] placeholder:text-[#8c909f] focus:border-[#4d8eff] focus:outline-none focus:ring-2 focus:ring-[#4d8eff]/30"
      />
      <button
        type="submit"
        disabled={pending || title.length === 0}
        className="rounded-xl bg-[#4d8eff] px-5 py-2.5 text-sm font-semibold text-[#00285d] transition-colors hover:bg-[#adc6ff] disabled:opacity-50"
      >
        {pending ? "Creating…" : "+ New notebook"}
      </button>
      {error && (
        <p className="self-center text-xs text-red-400" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
