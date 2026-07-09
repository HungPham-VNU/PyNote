"use client";

import { useState, useTransition } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { uploadSource } from "@/lib/api";

const MAX_MB = 30;

// Accepted upload types — must mirror CONTENT_TYPE_TO_KIND on the API. Some
// browsers send Office files as an empty/generic type, so we also allow by
// file extension as a fallback.
const ACCEPTED_MIME = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv",
]);
const ACCEPTED_EXT = [".pdf", ".pptx", ".xlsx", ".csv"];
const ACCEPT_ATTR = [...ACCEPTED_MIME, ...ACCEPTED_EXT].join(",");

function isAccepted(file: File): boolean {
  if (ACCEPTED_MIME.has(file.type)) return true;
  const name = file.name.toLowerCase();
  return ACCEPTED_EXT.some((ext) => name.endsWith(ext));
}

export function SourceUploader({ notebookId }: { notebookId: string }) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (file: File) => {
    setError(null);
    if (!isAccepted(file)) {
      setError("Accepted types: PDF, PowerPoint (.pptx), Excel (.xlsx), CSV.");
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
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 text-center text-xs transition-colors ${
          dragging
            ? "border-[#4d8eff] bg-[#4d8eff]/10"
            : "border-[#424754] hover:border-[#8c909f] hover:bg-[#201f20]"
        } ${pending ? "pointer-events-none opacity-60" : ""}`}
      >
        <span className="text-2xl text-[#8c909f]">↑</span>
        <span className="mt-1 font-medium text-[#e5e2e3]">
          {pending ? "Uploading…" : "Drag & Drop a file"}
        </span>
        <span className="mt-0.5 text-[#c2c6d6]">
          PDF · PPTX · XLSX · CSV — click to browse · max {MAX_MB}MB
        </span>
        <input
          type="file"
          accept={ACCEPT_ATTR}
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
        <p className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
