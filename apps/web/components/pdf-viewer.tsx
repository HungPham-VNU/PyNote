"use client";

type Props = {
  sourceId: string;
  initialPage?: number | null;
  citedText?: string | null;
};

export function PdfViewer({ sourceId, initialPage, citedText }: Props) {
  return (
    <div className="flex flex-col gap-2 p-4 border border-neutral-200 rounded-md bg-neutral-50">
      <h3 className="text-sm font-semibold text-neutral-800">Citation</h3>
      {citedText && (
        <blockquote className="text-sm text-neutral-600 border-l-4 border-neutral-300 pl-3 italic my-2">
          "{citedText}"
        </blockquote>
      )}
      {initialPage && (
        <p className="text-xs text-neutral-500">Source Page: {initialPage}</p>
      )}
    </div>
  );
}
