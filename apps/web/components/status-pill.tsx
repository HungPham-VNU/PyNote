import type { SourceStatus } from "@/lib/api";

const TONE: Record<SourceStatus, string> = {
  pending: "bg-[#2a2a2b] text-[#c2c6d6]",
  uploading: "bg-[#4d8eff]/20 text-[#adc6ff]",
  parsing: "bg-[#4d8eff]/20 text-[#adc6ff]",
  parsed: "bg-[#4d8eff]/20 text-[#adc6ff]",
  embedding: "bg-[#4d8eff]/20 text-[#adc6ff]",
  ready: "bg-[#4edea3]/20 text-[#4edea3]",
  failed: "bg-red-500/20 text-red-400",
};

export function StatusPill({ status }: { status: SourceStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${TONE[status]}`}
    >
      {status}
    </span>
  );
}
