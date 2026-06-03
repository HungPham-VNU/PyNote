"use client";

import type { Citation } from "@/lib/chat";

export function CitationPill({
  citation,
  index,
  onClick,
}: {
  citation: Citation;
  index: number;
  onClick: (c: Citation) => void;
}) {
  const tone = citation.roundtrip_ok
    ? "bg-blue-100 text-blue-800 hover:bg-blue-200"
    : "bg-amber-100 text-amber-800 hover:bg-amber-200";
  return (
    <button
      type="button"
      onClick={() => onClick(citation)}
      title={citation.cited_text}
      className={`mx-0.5 inline-flex items-center rounded-full px-1.5 text-[10px] font-semibold align-baseline transition-colors ${tone}`}
    >
      [{index + 1}]
    </button>
  );
}
