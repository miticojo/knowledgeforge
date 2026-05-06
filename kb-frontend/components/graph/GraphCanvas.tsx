"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useGraphStore, type GraphNode } from "@/lib/graph-store";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const LAYER_COLORS: Record<string, string> = {
  Strategy: "#d97706",
  Motivation: "#84cc16",
  Business: "#3b82f6",
  Application: "#f97316",
  Technology: "#10b981",
};

function colorForLayer(layer: string): string {
  return LAYER_COLORS[layer] || "#6b7280";
}

interface ForceNode extends GraphNode {
  x?: number;
  y?: number;
}

interface ForceLink {
  source: string | ForceNode;
  target: string | ForceNode;
  type: string;
  confidence?: number;
}

export default function GraphCanvas() {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const selection = useGraphStore((s) => s.selection);
  const toggleSelect = useGraphStore((s) => s.toggleSelect);
  const selectMany = useGraphStore((s) => s.selectMany);
  const clearSelection = useGraphStore((s) => s.clearSelection);
  const mergeSubGraph = useGraphStore((s) => s.mergeSubGraph);

  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<unknown>(null);
  const [dims, setDims] = useState({ w: 800, h: 600 });
  const [hovered, setHovered] = useState<{ node: ForceNode; x: number; y: number } | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      if (r.width > 0 && r.height > 0) setDims({ w: r.width, h: r.height });
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const graphData = useMemo(() => {
    const nodeIds = new Set(nodes.map((n) => n.id));
    return {
      nodes: nodes.map((n) => ({ ...n })),
      links: edges
        .filter((e) => nodeIds.has(e.source_id) && nodeIds.has(e.target_id))
        .map((e) => ({
          source: e.source_id,
          target: e.target_id,
          type: e.type,
          confidence: e.confidence,
        })) as ForceLink[],
    };
  }, [nodes, edges]);

  const handleNodeClick = useCallback(
    async (node: ForceNode, event: MouseEvent) => {
      // Cmd/Ctrl+click = expand neighborhood (advanced)
      if (event.metaKey || event.ctrlKey) {
        try {
          const res = await fetch(`/api/graph/neighborhood/${encodeURIComponent(node.id)}?hops=1`);
          if (res.ok) {
            const data = await res.json();
            mergeSubGraph(data);
          }
        } catch {
          // silent
        }
        return;
      }
      // Shift+click = additive selection
      // Plain click = toggle this entity in selection (default UX)
      toggleSelect(node.id);
    },
    [toggleSelect, mergeSubGraph]
  );

  // Keyboard: Cmd+A select all visible, Esc clear
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a") {
        if (document.activeElement === el || el.contains(document.activeElement)) {
          e.preventDefault();
          selectMany(nodes.map((n) => n.id));
        }
      } else if (e.key === "Escape") {
        clearSelection();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [nodes, selectMany, clearSelection]);

  const paintNode = useCallback(
    (node: ForceNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const color = colorForLayer(node.layer);
      const selected = selection.has(node.id);
      const r = selected ? 8 : 5;
      ctx.beginPath();
      ctx.arc(node.x || 0, node.y || 0, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
      if (selected) {
        ctx.strokeStyle = "#fbbf24";
        ctx.lineWidth = 2;
        ctx.stroke();
      } else {
        ctx.strokeStyle = "rgba(255,255,255,0.4)";
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
      if (scale > 1.2) {
        const fontSize = Math.max(10 / scale, 3);
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        ctx.fillText(node.name, node.x || 0, (node.y || 0) + r + 2);
      }
    },
    [selection]
  );

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      data-testid="graph-canvas"
      className="relative w-full h-full min-h-0 outline-none focus-visible:ring-2 focus-visible:ring-orange-500/40 bg-slate-950/40"
    >
      {hovered && (
        <div
          className="pointer-events-none absolute z-20 px-3 py-2 rounded-lg bg-black/80 border border-white/10 backdrop-blur-md text-[11px] text-white shadow-2xl"
          style={{ left: hovered.x + 12, top: hovered.y + 12 }}
        >
          <div className="font-semibold">{hovered.node.name}</div>
          <div className="text-white/60">
            {hovered.node.type} &middot;{" "}
            <span style={{ color: colorForLayer(hovered.node.layer) }}>
              {hovered.node.layer}
            </span>
          </div>
        </div>
      )}

      <div className="absolute top-3 right-3 z-20 bg-black/60 backdrop-blur-sm rounded-xl px-3 py-2 border border-white/10 text-[10px] text-white/60">
        {nodes.length} nodes &middot; {graphData.links.length} edges
        {selection.size > 0 && (
          <span className="ml-2 text-amber-400">{selection.size} selected</span>
        )}
      </div>

      <div className="absolute bottom-3 left-3 z-20 flex flex-wrap gap-1.5">
        {Object.entries(LAYER_COLORS).map(([layer, color]) => (
          <div
            key={layer}
            className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-black/50 border border-white/10 backdrop-blur-sm text-[10px] text-white/70"
          >
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            {layer}
          </div>
        ))}
      </div>

      <ForceGraph2D
        ref={fgRef as never}
        graphData={graphData}
        width={dims.w}
        height={dims.h}
        backgroundColor="transparent"
        nodeRelSize={5}
        nodeCanvasObject={paintNode as never}
        nodePointerAreaPaint={((node: ForceNode, color: string, ctx: CanvasRenderingContext2D) => {
          ctx.beginPath();
          ctx.arc(node.x || 0, node.y || 0, 10, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }) as never}
        linkColor={() => "rgba(255,255,255,0.15)"}
        linkWidth={0.6}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={0.85}
        cooldownTicks={120}
        onNodeClick={handleNodeClick as never}
        onNodeHover={((node: ForceNode | null) => {
          if (!node) {
            setHovered(null);
            return;
          }
          const rect = containerRef.current?.getBoundingClientRect();
          if (!rect) return;
          setHovered({ node, x: dims.w / 2, y: dims.h / 2 });
        }) as never}
        onBackgroundClick={() => setHovered(null)}
      />
    </div>
  );
}
