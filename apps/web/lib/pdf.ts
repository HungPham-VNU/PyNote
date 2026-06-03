/** PDF.js worker bootstrap.
 *
 * Pinned to the react-pdf bundled pdfjs version. Loading from a CDN keeps
 * the Next.js bundle small in dev; swap to a self-hosted asset for prod by
 * copying `pdfjs-dist/build/pdf.worker.min.mjs` into /public/.
 */

import { pdfjs } from "react-pdf";

export function configurePdfWorker(): void {
  if (typeof window === "undefined") return;
  pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Fetch the PDF bytes with a Clerk bearer token, return an object URL. */
export async function fetchPdfBlobUrl(
  token: string | null,
  sourceId: string,
): Promise<string> {
  const res = await fetch(`${API_BASE}/api/v1/sources/${sourceId}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new Error(`PDF HTTP ${res.status}: ${await res.text()}`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

// ---- highlight helpers ----------------------------------------------------

const HIGHLIGHT_NAME = "pynote-citation";

/** Walk the text layer of one PDF page, find `cited`, set a CSS Highlight.
 *
 * Returns true if a highlight was set (target text found), false otherwise.
 * Browsers without CSS Custom Highlight API silently no-op — the page still
 * opens at the right number, just without the highlight.
 */
export function highlightCitedTextInPage(
  pageContainer: HTMLElement,
  cited: string,
): boolean {
  if (!supportsCustomHighlights()) return false;
  if (!cited.trim()) return false;

  const textLayer = pageContainer.querySelector(
    ".react-pdf__Page__textContent",
  );
  if (!textLayer) return false;

  // Walk every text node inside the text layer in document order, building
  // a flat string with a map from offset → (node, offset-within-node).
  const nodes: { node: Text; start: number; end: number }[] = [];
  let flat = "";
  const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
  for (
    let cur = walker.nextNode();
    cur;
    cur = walker.nextNode()
  ) {
    const text = (cur as Text).data;
    if (!text) continue;
    nodes.push({ node: cur as Text, start: flat.length, end: flat.length + text.length });
    flat += text;
  }

  const idx = locateApproximate(flat, cited);
  if (idx < 0) return false;

  const start = idx;
  const end = idx + cited.length;

  const startNode = nodes.find((n) => start >= n.start && start < n.end);
  const endNode = nodes.find((n) => end > n.start && end <= n.end);
  if (!startNode || !endNode) return false;

  const range = new Range();
  range.setStart(startNode.node, start - startNode.start);
  range.setEnd(endNode.node, end - endNode.start);

  const Highlight = (window as unknown as { Highlight: new (...args: Range[]) => unknown })
    .Highlight;
  // CSS.highlights is a registry; CSS namespace is available globally.
  const cssAny = (window as unknown as { CSS: { highlights?: Map<string, unknown> } }).CSS;
  if (!Highlight || !cssAny?.highlights) return false;
  cssAny.highlights.set(HIGHLIGHT_NAME, new Highlight(range));
  return true;
}

export function clearCitationHighlight(): void {
  if (!supportsCustomHighlights()) return;
  const cssAny = (window as unknown as { CSS: { highlights?: Map<string, unknown> } }).CSS;
  cssAny?.highlights?.delete(HIGHLIGHT_NAME);
}

function supportsCustomHighlights(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof (window as unknown as { Highlight?: unknown }).Highlight !== "undefined"
  );
}

/** Locate `needle` inside `haystack` tolerating whitespace differences.
 *
 * PDF.js often splits text across spans with extra spaces; an exact
 * substring search misses. We collapse whitespace on both sides and map the
 * collapsed match back to the original offset.
 */
function locateApproximate(haystack: string, needle: string): number {
  const exact = haystack.indexOf(needle);
  if (exact >= 0) return exact;

  const collapsedNeedle = needle.replace(/\s+/g, " ").trim();
  if (!collapsedNeedle) return -1;

  // Build a mapping from collapsed-haystack offset → original-haystack offset.
  let collapsed = "";
  const map: number[] = [];
  let inWs = false;
  for (let i = 0; i < haystack.length; i++) {
    const ch = haystack[i];
    if (/\s/.test(ch)) {
      if (!inWs && collapsed.length > 0) {
        collapsed += " ";
        map.push(i);
      }
      inWs = true;
    } else {
      collapsed += ch;
      map.push(i);
      inWs = false;
    }
  }
  const hit = collapsed.indexOf(collapsedNeedle);
  if (hit < 0) return -1;
  return map[hit] ?? -1;
}
