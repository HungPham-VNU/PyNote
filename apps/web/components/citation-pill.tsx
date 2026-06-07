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
    ? "bg-[#4d8eff]/30 text-[#adc6ff] hover:bg-[#4d8eff]/50"
    : "bg-[#fcd34d]/20 text-[#fcd34d] hover:bg-[#fcd34d]/30";
  return (
    <button
      type="button"
      onClick={() => onClick(citation)}
      title={citation.cited_text}
      className={`mx-0.5 inline-flex items-center rounded-md px-1.5 align-baseline text-[10px] font-semibold transition-colors ${tone}`}
    >
      [{index + 1}]
    </button>
  );
}
