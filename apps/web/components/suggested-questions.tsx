"use client";

import { useMemo } from "react";
import type { Source } from "@/lib/api";

const FILL_EVENT = "pynote:fill-chat" as const;
const MAX_CHIPS = 6;
const PER_SOURCE_MAX = 2;

/** Trigger ChatPanel to drop a string into its input. */
export function emitFillChat(text: string): void {
  window.dispatchEvent(new CustomEvent(FILL_EVENT, { detail: text }));
}

export const FILL_CHAT_EVENT = FILL_EVENT;

export function SuggestedQuestions({ sources }: { sources: Source[] }) {
  const chips = useMemo<{ text: string; sourceTitle: string }[]>(() => {
    const out: { text: string; sourceTitle: string }[] = [];
    const seen = new Set<string>();
    for (const s of sources) {
      const qs = s.meta?.suggested_questions ?? [];
      let taken = 0;
      for (const q of qs) {
        if (taken >= PER_SOURCE_MAX) break;
        const k = q.trim().toLowerCase();
        if (!k || seen.has(k)) continue;
        seen.add(k);
        out.push({ text: q.trim(), sourceTitle: s.title });
        taken += 1;
        if (out.length >= MAX_CHIPS) break;
      }
      if (out.length >= MAX_CHIPS) break;
    }
    return out;
  }, [sources]);

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c, i) => (
        <button
          key={i}
          type="button"
          title={`From: ${c.sourceTitle}`}
          onClick={() => emitFillChat(c.text)}
          className="rounded-full border border-[#424754] bg-[#201f20] px-3 py-1 text-[11px] text-[#e5e2e3] transition-colors hover:border-[#4d8eff] hover:bg-[#4d8eff]/10 hover:text-[#adc6ff]"
        >
          {c.text}
        </button>
      ))}
    </div>
  );
}
