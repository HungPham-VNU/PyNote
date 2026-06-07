"use client";

import { useEffect } from "react";
import { PdfViewer } from "@/components/pdf-viewer";

export type DrawerTarget = {
  sourceId: string;
  sourceTitle: string | null;
  page: number | null;
  citedText: string;
};

export function SourceDrawer({
  target,
  onClose,
}: {
  target: DrawerTarget | null;
  onClose: () => void;
}) {
  // Close on Esc.
  useEffect(() => {
    if (!target) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target, onClose]);

  if (!target) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex"
      role="dialog"
      aria-modal="true"
      data-no-select
    >
      <button
        type="button"
        aria-label="Close source viewer"
        onClick={onClose}
        className="flex-1 bg-black/30 transition-opacity"
      />
      <aside className="flex h-full w-full max-w-[780px] flex-col gap-3 overflow-y-auto bg-[#1c1b1c] p-5 shadow-2xl">
        <header className="flex items-center justify-between gap-3 border-b border-[#424754] pb-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-[#e5e2e3]">
              {target.sourceTitle ?? "Source"}
            </h2>
            {target.page && (
              <p className="text-xs text-[#c2c6d6]">Page {target.page}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[#424754] px-3 py-1 text-xs text-[#e5e2e3] hover:bg-[#2a2a2b]"
          >
            Close
          </button>
        </header>

        <section className="rounded-lg border border-[#fcd34d]/30 bg-[#fcd34d]/10 px-3 py-2 text-xs text-[#fcd34d]">
          <span className="font-semibold">Cited passage:</span>{" "}
          <span className="italic">“{target.citedText}”</span>
        </section>

        <PdfViewer
          sourceId={target.sourceId}
          initialPage={target.page}
          citedText={target.citedText}
        />
      </aside>
    </div>
  );
}
