import type { SourceStatus } from "@/lib/api";

const TONE: Record<SourceStatus, string> = {
  pending: "bg-neutral-100 text-neutral-700",
  uploading: "bg-blue-100 text-blue-800",
  parsing: "bg-amber-100 text-amber-800",
  parsed: "bg-green-100 text-green-800",
  embedding: "bg-amber-100 text-amber-800",
  ready: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export function StatusPill({ status }: { status: SourceStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONE[status]}`}
    >
      {status}
    </span>
  );
}
