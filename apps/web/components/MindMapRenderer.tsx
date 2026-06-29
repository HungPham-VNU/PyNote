"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { toPng } from "html-to-image";
import {
  type MindMap,
  type MindMapCitation,
  type MindMapEdge,
  type MindMapNode,
  generateMindMap,
  getMindMap,
} from "@/lib/api";

const NODE_WIDTH = 200;
const NODE_HEIGHT = 56;
const POLL_MS = 3000;

const KIND_COLOR: Record<string, string> = {
  concept: "#4d8eff",
  entity: "#34d399",
  person: "#f472b6",
  event: "#fbbf24",
  claim: "#a78bfa",
};

function kindColor(kind: string): string {
  return KIND_COLOR[kind] ?? "#8c909f";
}

type ActiveElement =
  | { type: "node"; node: MindMapNode }
  | { type: "edge"; edge: MindMapEdge }
  | null;

function layoutWithDagre(
  nodes: MindMapNode[],
  edges: MindMapEdge[],
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 90 });

  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const e of edges) {
    if (g.hasNode(e.from) && g.hasNode(e.to)) g.setEdge(e.from, e.to);
  }
  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { label: n.label },
      style: {
        width: NODE_WIDTH,
        border: `1.5px solid ${kindColor(n.kind)}`,
        borderRadius: 10,
        background: "#201f20",
        color: "#e5e2e3",
        fontSize: 12,
        padding: 8,
      },
    };
  });
}

function toFlowEdges(edges: MindMapEdge[]): Edge[] {
  return edges.map((e, i) => ({
    id: `edge-${i}`,
    source: e.from,
    target: e.to,
    label: e.label,
    data: { edgeIndex: i },
    style: { stroke: "#424754" },
    labelStyle: { fill: "#c2c6d6", fontSize: 10 },
    labelBgStyle: { fill: "#1c1b1c" },
    animated: false,
  }));
}

export function MindMapRenderer({
  notebookId,
  hasReadySource,
}: {
  notebookId: string;
  hasReadySource: boolean;
}) {
  const { getToken } = useAuth();
  const [mindMap, setMindMap] = useState<MindMap | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchOnce = useCallback(async () => {
    const token = await getToken();
    const cur = await getMindMap(token, notebookId);
    setMindMap(cur);
    if (cur?.status === "generating") {
      pollRef.current = setTimeout(fetchOnce, POLL_MS);
    }
    return cur;
  }, [getToken, notebookId]);

  useEffect(() => {
    fetchOnce().catch(() => {
      // Best-effort initial fetch — the generate button still works without it.
    });
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notebookId]);

  const handleGenerate = useCallback(async () => {
    setError(null);
    setLoading(true);
    stopPolling();
    try {
      const token = await getToken();
      const started = await generateMindMap(token, notebookId);
      setMindMap(started);
      pollRef.current = setTimeout(fetchOnce, POLL_MS);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [getToken, notebookId, fetchOnce, stopPolling]);

  const handleExportPng = useCallback(async () => {
    const el = wrapperRef.current?.querySelector(
      ".react-flow__viewport",
    ) as HTMLElement | null;
    if (!el) return;
    const dataUrl = await toPng(el, { backgroundColor: "#1c1b1c" });
    const link = document.createElement("a");
    link.download = `mind-map-${notebookId}.png`;
    link.href = dataUrl;
    link.click();
  }, [notebookId]);

  const nodes = useMemo(
    () => layoutWithDagre(mindMap?.nodes ?? [], mindMap?.edges ?? []),
    [mindMap],
  );
  const edges = useMemo(() => toFlowEdges(mindMap?.edges ?? []), [mindMap]);

  const onNodeClick = useCallback(
    (_: unknown, flowNode: Node) => {
      const found = mindMap?.nodes.find((n) => n.id === flowNode.id);
      if (found) setActive({ type: "node", node: found });
    },
    [mindMap],
  );

  const onEdgeClick = useCallback(
    (_: unknown, flowEdge: Edge) => {
      const idx = (flowEdge.data as { edgeIndex?: number } | undefined)?.edgeIndex;
      const found = idx !== undefined ? mindMap?.edges[idx] : undefined;
      if (found) setActive({ type: "edge", edge: found });
    },
    [mindMap],
  );

  const isGenerating = loading || mindMap?.status === "generating";
  const hasMap = mindMap?.status === "ready" && mindMap.nodes.length > 0;

  return (
    <div className="flex flex-col gap-2" data-no-select>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleGenerate}
          disabled={isGenerating || !hasReadySource}
          className="rounded-xl bg-[#fcd34d] px-4 py-2 text-sm font-semibold text-[#3a2a00] transition-colors hover:bg-[#fde68a] disabled:opacity-50"
          title={!hasReadySource ? "Add a ready source first" : "Generate a mind map"}
        >
          {isGenerating
            ? "Mapping…"
            : hasMap
              ? "↻ Re-generate mind map"
              : "✦ Generate mind map"}
        </button>
        {hasMap && (
          <button
            type="button"
            onClick={handleExportPng}
            className="rounded-xl border border-[#424754] bg-[#201f20] px-3 py-2 text-xs text-[#e5e2e3] transition-colors hover:border-[#8c909f] hover:bg-[#2a2a2b]"
          >
            Export PNG
          </button>
        )}
        {mindMap?.generated_at && mindMap.status === "ready" && (
          <span className="text-xs text-[#c2c6d6]">
            Updated {new Date(mindMap.generated_at).toLocaleString()}
          </span>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}
      {mindMap?.status === "failed" && (
        <p className="text-xs text-red-400" role="alert">
          {mindMap.error ?? "Mind map generation failed."}
        </p>
      )}

      {hasMap && (
        <div className="flex h-[560px] gap-3">
          <div
            ref={wrapperRef}
            className="relative flex-1 overflow-hidden rounded-xl border border-[#424754] bg-[#1c1b1c]"
          >
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodeClick={onNodeClick}
              onEdgeClick={onEdgeClick}
              fitView
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#2a2a2b" gap={20} />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                style={{ background: "#201f20" }}
                maskColor="rgba(0,0,0,0.6)"
              />
            </ReactFlow>
          </div>

          {active && (
            <aside className="w-[320px] shrink-0 overflow-y-auto rounded-xl border border-[#424754] bg-[#201f20] p-4">
              <div className="mb-3 flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-[#e5e2e3]">
                  {active.type === "node" ? active.node.label : active.edge.label}
                </h3>
                <button
                  type="button"
                  onClick={() => setActive(null)}
                  className="rounded-lg border border-[#424754] px-2 py-0.5 text-xs text-[#e5e2e3] hover:bg-[#2a2a2b]"
                >
                  Close
                </button>
              </div>
              {active.type === "node" && (
                <p className="mb-3 text-[10px] uppercase tracking-wider text-[#c2c6d6]">
                  {active.node.kind}
                </p>
              )}
              {active.type === "edge" && (
                <p className="mb-3 text-[10px] uppercase tracking-wider text-[#c2c6d6]">
                  {active.edge.from} → {active.edge.to}
                </p>
              )}
              <CitationList
                citations={
                  active.type === "node" ? active.node.citations : active.edge.citations
                }
              />
            </aside>
          )}
        </div>
      )}

      {!hasMap && mindMap?.status !== "generating" && !loading && (
        <p className="text-xs text-[#8c909f]">
          No mind map yet — generate one to see concepts and relationships across this
          notebook&apos;s sources.
        </p>
      )}
    </div>
  );
}

function CitationList({ citations }: { citations: MindMapCitation[] }) {
  if (citations.length === 0) {
    return <p className="text-xs text-[#8c909f]">No citations.</p>;
  }
  return (
    <ul className="space-y-3">
      {citations.map((c, i) => (
        <li key={i} className="rounded-lg border border-[#424754] p-2.5">
          <p className="mb-1 flex items-center justify-between gap-2 text-[10px] text-[#c2c6d6]">
            <span className="truncate">
              {c.source_title ?? "Untitled source"}
              {c.page ? ` · p.${c.page}` : ""}
            </span>
            <span
              className={c.roundtrip_ok ? "text-emerald-400" : "text-amber-400"}
              title={c.roundtrip_ok ? "Quote verified in source" : "Quote could not be verified"}
            >
              {c.roundtrip_ok ? "✓ verified" : "⚠ unverified"}
            </span>
          </p>
          <p className="text-xs italic leading-relaxed text-[#e5e2e3]">“{c.quote}”</p>
        </li>
      ))}
    </ul>
  );
}
