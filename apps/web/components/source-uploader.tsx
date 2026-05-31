"use client";

import { useState, useTransition } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { uploadSource } from "@/lib/api";

const MAX_MB = 30;

export function SourceUploader({ notebookId }: { notebookId: string }) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (file: File) => {
    setError(null);
    if (file.type !== "application/pdf") {
      setError("Only PDF accepted in M1.");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`File exceeds ${MAX_MB}MB limit.`);
      return;
    }
    startTransition(async () => {
      try {
        const token = await getToken();
        await uploadSource(token, notebookId, file);
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Upload failed");
      }
    });
  };

  return (
    <div className="space-y-2">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) submit(f);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed px-6 py-10 text-center text-sm transition-colors ${
          dragging
            ? "border-neutral-900 bg-neutral-100"
            : "border-neutral-300 hover:bg-neutral-50"
        } ${pending ? "pointer-events-none opacity-60" : ""}`}
      >
        <span className="font-medium">
          {pending ? "Uploading…" : "Drop a PDF here, or click to choose"}
        </span>
        <span className="mt-1 text-xs text-neutral-500">
          PDF only, up to {MAX_MB}MB
        </span>
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          disabled={pending}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) submit(f);
            e.target.value = "";
          }}
        />
      </label>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
