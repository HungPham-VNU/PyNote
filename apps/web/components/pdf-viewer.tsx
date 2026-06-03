"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { Document, Page } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import {
  clearCitationHighlight,
  configurePdfWorker,
  fetchPdfBlobUrl,
  highlightCitedTextInPage,
} from "@/lib/pdf";

configurePdfWorker();

type Props = {
  sourceId: string;
  initialPage?: number | null;
  citedText?: string | null;
};

export function PdfViewer({ sourceId, initialPage, citedText }: Props) {
  const { getToken } = useAuth();
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [page, setPage] = useState<number>(initialPage ?? 1);
  const [error, setError] = useState<string | null>(null);
  const [highlightStatus, setHighlightStatus] = useState<"hit" | "miss" | "none">(
    "none",
  );
  const pageRef = useRef<HTMLDivElement | null>(null);

  // ---- fetch the PDF bytes once per source (with Clerk token)
  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    setError(null);
    setBlobUrl(null);
    (async () => {
      try {
        const token = await getToken();
        url = await fetchPdfBlobUrl(token, sourceId);
        if (!cancelled) setBlobUrl(url);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [sourceId, getToken]);

  // ---- jump page when citation changes
  useEffect(() => {
    if (initialPage && initialPage > 0) setPage(initialPage);
  }, [initialPage]);

  // ---- highlight the cited text after the page renders
  const onPageRender = () => {
    clearCitationHighlight();
    if (!citedText || !pageRef.current) {
      setHighlightStatus("none");
      return;
    }
    const ok = highlightCitedTextInPage(pageRef.current, citedText);
    setHighlightStatus(ok ? "hit" : "miss");
  };

  // ---- cleanup highlight on unmount
  useEffect(() => () => clearCitationHighlight(), []);

  if (error) {
    return (
      <p className="px-4 py-3 text-sm text-red-700" role="alert">
        {error}
      </p>
    );
  }
  if (!blobUrl) {
    return (
      <p className="px-4 py-3 text-sm text-neutral-500">Loading PDF…</p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2 px-1 text-xs text-neutral-600">
        <button
          type="button"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
          className="rounded border border-neutral-300 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40"
        >
          ‹ Prev
        </button>
        <span>
          Page {page}
          {numPages ? ` / ${numPages}` : ""}
          {highlightStatus === "miss" && (
            <span
              className="ml-2 text-amber-700"
              title="Page opened but the cited text wasn't found verbatim — likely PDF text-layer drift."
            >
              (highlight unavailable)
            </span>
          )}
        </span>
        <button
          type="button"
          onClick={() => setPage((p) => (numPages ? Math.min(numPages, p + 1) : p + 1))}
          disabled={numPages !== null && page >= numPages}
          className="rounded border border-neutral-300 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40"
        >
          Next ›
        </button>
      </div>

      <div ref={pageRef} className="overflow-auto rounded-md border border-neutral-200">
        <Document
          file={blobUrl}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          onLoadError={(e) => setError(e.message)}
          loading={<div className="p-4 text-sm text-neutral-500">Parsing PDF…</div>}
        >
          <Page
            pageNumber={page}
            width={680}
            renderTextLayer
            renderAnnotationLayer={false}
            onRenderSuccess={onPageRender}
          />
        </Document>
      </div>
    </div>
  );
}
