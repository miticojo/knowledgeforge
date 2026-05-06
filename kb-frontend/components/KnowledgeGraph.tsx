"use client";

import { useRef, useMemo, useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

// ---------------------------------------------------------------------------
// ArchiMate 3.2 Wave 2 — Layer definitions & colors
// ---------------------------------------------------------------------------

const ARCHIMATE_LAYERS = {
  Strategy:   { order: 0, color: "#d97706", y: 0.05 },
  Motivation: { order: 1, color: "#84cc16", y: 0.20 },
  Business:   { order: 2, color: "#3b82f6", y: 0.45 },
  Application:{ order: 3, color: "#f97316", y: 0.70 },
  Technology: { order: 4, color: "#10b981", y: 0.90 },
} as const;

type LayerName = keyof typeof ARCHIMATE_LAYERS;

const ENTITY_LAYER_MAP: Record<string, LayerName> = {
  Capability: "Strategy",
  BusinessActor: "Business", BusinessRole: "Business",
  BusinessProcess: "Business", BusinessFunction: "Business",
  BusinessService: "Business", BusinessObject: "Business", Contract: "Business",
  ApplicationComponent: "Application", ApplicationService: "Application",
  ApplicationInterface: "Application", DataObject: "Application",
  Node: "Technology", Device: "Technology", SystemSoftware: "Technology",
  TechnologyService: "Technology", Artifact: "Technology",
  CommunicationNetwork: "Technology",
  Goal: "Motivation", Requirement: "Motivation", Constraint: "Motivation",
  Stakeholder: "Motivation",
};

// Colori per tipo ArchiMate 3.2 Wave 2 (22 tipi + default)
const TYPE_COLORS: Record<string, string> = {
  // Strategy
  Capability: "#d97706",
  // Business
  BusinessActor: "#3b82f6", BusinessRole: "#60a5fa",
  BusinessProcess: "#06b6d4", BusinessFunction: "#0891b2",
  BusinessService: "#22d3ee", BusinessObject: "#67e8f9", Contract: "#2dd4bf",
  // Application
  ApplicationComponent: "#f97316", ApplicationService: "#fb923c",
  ApplicationInterface: "#fdba74", DataObject: "#8b5cf6",
  // Technology
  Node: "#ef4444", Device: "#f87171", SystemSoftware: "#ec4899",
  TechnologyService: "#14b8a6", Artifact: "#f472b6",
  CommunicationNetwork: "#a78bfa",
  // Motivation
  Goal: "#eab308", Requirement: "#facc15", Constraint: "#fde047",
  Stakeholder: "#a3e635",
  default: "#6b7280",
};

// ---------------------------------------------------------------------------
// Parsing helpers
// ---------------------------------------------------------------------------

function parseNodeString(raw: string): { type: string; name: string } {
  const colonIdx = raw.indexOf(":");
  if (colonIdx > 0) {
    const candidateType = raw.substring(0, colonIdx).trim();
    if (TYPE_COLORS[candidateType]) {
      return { type: candidateType, name: raw.substring(colonIdx + 1).trim() };
    }
  }
  return { type: "default", name: raw.trim() };
}

function parseEdgeString(raw: string): { sourceKey: string; targetKey: string; label: string } | null {
  const parts = raw.split("->");
  if (parts.length < 3) return null;
  const sourceRaw = parts[0].trim();
  const label = parts[1].trim();
  const targetRaw = parts.slice(2).join("->").trim();
  const cleanLabel = label.replace(/\[.*\]/, "").trim();
  return { sourceKey: sourceRaw, targetKey: targetRaw, label: cleanLabel };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface KnowledgeGraphProps {
  graphData: {
    extracted_nodes?: string[];
    extracted_edges?: string[];
    total_nodes?: number;
    total_edges?: number;
    // Legacy keys for backward compatibility
    NodiEstratti?: string[];
    ArchiGenerati?: string[];
    ArchiEstratti?: string[];
    nodi_estratti?: string[];
    archi_generati?: string[];
    archi_estratti?: string[];
  };
  width?: number;
  height?: number;
}

export default function KnowledgeGraph({ graphData, width = 700, height = 500 }: KnowledgeGraphProps) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ w: width, h: height });
  const [hiddenLayers, setHiddenLayers] = useState<Set<LayerName>>(new Set());
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const initializedRef = useRef(false);

  const rawNodes = graphData.extracted_nodes || graphData.NodiEstratti || graphData.nodi_estratti || [];
  const rawEdges = graphData.extracted_edges || graphData.ArchiEstratti || graphData.archi_estratti || graphData.ArchiGenerati || graphData.archi_generati || [];

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const { width: w, height: h } = entries[0].contentRect;
      if (w > 0 && h > 0) setDimensions({ w, h });
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  // ---------------------------------------------------------------------------
  // Build graph data
  // ---------------------------------------------------------------------------
  const { allNodes, allLinks, activeTypes, activeLayers } = useMemo(() => {
    const nodeById = new Map<string, { id: string; name: string; type: string; layer: LayerName; linkCount: number }>();
    for (const raw of rawNodes) {
      const { type, name } = parseNodeString(raw);
      if (TYPE_COLORS[raw] && raw !== "default") continue;
      const layer = ENTITY_LAYER_MAP[type] || "Technology";
      nodeById.set(raw, { id: raw, name, type, layer, linkCount: 0 });
    }

    const allLinks: { source: string; target: string; label: string }[] = [];
    for (const raw of rawEdges) {
      const parsed = parseEdgeString(raw);
      if (!parsed || parsed.label === "E_UN") continue;
      if (nodeById.has(parsed.sourceKey) && nodeById.has(parsed.targetKey)) {
        allLinks.push({ source: parsed.sourceKey, target: parsed.targetKey, label: parsed.label });
        nodeById.get(parsed.sourceKey)!.linkCount++;
        nodeById.get(parsed.targetKey)!.linkCount++;
      }
    }

    const allNodes = Array.from(nodeById.values());
    const activeTypes = new Set(allNodes.map((n) => n.type).filter((t) => t !== "default"));
    const activeLayers = new Set(allNodes.map((n) => n.layer));

    return { allNodes, allLinks, activeTypes, activeLayers };
  }, [rawNodes, rawEdges]);

  // ---------------------------------------------------------------------------
  // Apply layer filter
  // ---------------------------------------------------------------------------
  const { nodes, links, maxLinkCount } = useMemo(() => {
    const visibleIds = new Set<string>();
    const nodes = allNodes.filter((n) => {
      if (hiddenLayers.has(n.layer)) return false;
      visibleIds.add(n.id);
      return true;
    });
    const links = allLinks.filter((l) => {
      // react-force-graph muta source/target da stringa a oggetto dopo il render
      const srcId = typeof l.source === "string" ? l.source : (l.source as any)?.id;
      const tgtId = typeof l.target === "string" ? l.target : (l.target as any)?.id;
      return visibleIds.has(srcId) && visibleIds.has(tgtId);
    });
    const maxLinkCount = Math.max(1, ...nodes.map((n) => n.linkCount));
    return { nodes, links, maxLinkCount };
  }, [allNodes, allLinks, hiddenLayers]);

  // ---------------------------------------------------------------------------
  // Initial positioning by layer (Y-axis clustering) + zoom to fit
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!fgRef.current || nodes.length === 0 || initializedRef.current) return;
    initializedRef.current = true;

    // Pre-position nodes by layer Y band with random X spread
    const h = dimensions.h;
    const w = dimensions.w;
    for (const node of nodes as any[]) {
      const layerDef = ARCHIMATE_LAYERS[node.layer as LayerName];
      const yCenter = layerDef ? layerDef.y * h : h / 2;
      node.x = (Math.random() - 0.5) * w * 0.8;
      node.y = yCenter + (Math.random() - 0.5) * h * 0.12;
    }

    // Reheat simulation from these positions
    fgRef.current.d3ReheatSimulation();
    setTimeout(() => fgRef.current?.zoomToFit(400, 50), 800);
  }, [nodes.length, dimensions]);

  // Reset initialization when data changes
  useEffect(() => {
    initializedRef.current = false;
  }, [rawNodes, rawEdges]);

  // ---------------------------------------------------------------------------
  // Hover neighbors
  // ---------------------------------------------------------------------------
  const neighborSet = useMemo(() => {
    if (!hoveredNode) return null;
    const s = new Set<string>([hoveredNode]);
    for (const l of allLinks) {
      const src = typeof l.source === "string" ? l.source : (l.source as any).id;
      const tgt = typeof l.target === "string" ? l.target : (l.target as any).id;
      if (src === hoveredNode) s.add(tgt);
      if (tgt === hoveredNode) s.add(src);
    }
    return s;
  }, [hoveredNode, allLinks]);

  // ---------------------------------------------------------------------------
  // Canvas rendering
  // ---------------------------------------------------------------------------
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const label = node.name as string;
    const type = node.type as string;
    const color = TYPE_COLORS[type] || TYPE_COLORS.default;
    const linkCount = node.linkCount || 0;
    const minSize = 4;
    const maxSize = 14;
    const size = minSize + (linkCount / (maxLinkCount || 1)) * (maxSize - minSize);

    // Dim nodes not in hover neighborhood
    const dimmed = neighborSet && !neighborSet.has(node.id);
    const alpha = dimmed ? 0.1 : 1;

    // Node circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
    ctx.fillStyle = dimmed ? `rgba(107,114,128,${alpha})` : color;
    ctx.fill();
    ctx.strokeStyle = `rgba(255,255,255,${alpha * 0.4})`;
    ctx.lineWidth = 0.5;
    ctx.stroke();

    // Label (only when zoomed enough or node is hovered/neighbor)
    const showLabel = globalScale > 0.6 || (neighborSet && neighborSet.has(node.id));
    if (showLabel) {
      const fontSize = Math.max(10 / globalScale, 2.5);
      ctx.font = `bold ${fontSize}px Inter, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = `rgba(255,255,255,${dimmed ? 0.08 : 0.9})`;
      ctx.fillText(label, node.x, node.y + size + 2);
    }
  }, [maxLinkCount, neighborSet]);

  const paintLink = useCallback((link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const start = link.source;
    const end = link.target;
    if (!start.x || !end.x) return;

    const srcId = typeof start === "string" ? start : start.id;
    const tgtId = typeof end === "string" ? end : end.id;
    const highlighted = neighborSet && neighborSet.has(srcId) && neighborSet.has(tgtId);
    const dimmed = neighborSet && !highlighted;

    // Line
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.strokeStyle = dimmed
      ? "rgba(255,255,255,0.02)"
      : highlighted
        ? "rgba(255,255,255,0.4)"
        : "rgba(255,255,255,0.1)";
    ctx.lineWidth = highlighted ? 1.5 : 0.6;
    ctx.stroke();

    // Label on edge (only when zoomed and not dimmed)
    if (globalScale > 1.0 && !dimmed) {
      const midX = (start.x + end.x) / 2;
      const midY = (start.y + end.y) / 2;
      const fontSize = Math.max(7 / globalScale, 2);
      ctx.font = `${fontSize}px Inter, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = highlighted ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.25)";
      ctx.fillText(link.label || "", midX, midY);
    }
  }, [neighborSet]);

  // ---------------------------------------------------------------------------
  // Toggle layer
  // ---------------------------------------------------------------------------
  const toggleLayer = (layer: LayerName) => {
    setHiddenLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  };

  // ---------------------------------------------------------------------------
  // Empty state
  // ---------------------------------------------------------------------------
  if (allNodes.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
        No graph data available
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex-1 relative w-full h-full min-h-0">

      {/* Legend — only active types, 3-col */}
      {activeTypes.size > 0 && (
        <div className="absolute top-3 left-3 z-20 bg-black/60 backdrop-blur-sm rounded-xl p-3 border border-white/10 max-w-[520px]">
          <p className="text-[9px] font-bold uppercase tracking-widest text-white/50 mb-2">ArchiMate Legend</p>
          <div className={`grid gap-x-4 gap-y-1 ${activeTypes.size > 8 ? "grid-cols-3" : "grid-cols-2"}`}>
            {Array.from(activeTypes).sort().map((type) => (
              <div key={type} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: TYPE_COLORS[type] || TYPE_COLORS.default }} />
                <span className="text-[10px] text-white/70">{type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Layer filter toggle buttons */}
      <div className="absolute bottom-3 left-3 z-20 flex gap-1.5">
        {(Object.entries(ARCHIMATE_LAYERS) as [LayerName, typeof ARCHIMATE_LAYERS[LayerName]][])
          .filter(([layer]) => activeLayers.has(layer))
          .map(([layer, def]) => {
            const hidden = hiddenLayers.has(layer);
            const count = allNodes.filter((n) => n.layer === layer).length;
            return (
              <button
                key={layer}
                onClick={() => toggleLayer(layer)}
                className={`text-[10px] px-2.5 py-1.5 rounded-lg border transition-all ${
                  hidden
                    ? "bg-black/40 border-white/5 text-white/30"
                    : "bg-black/60 border-white/15 text-white/80 backdrop-blur-sm"
                }`}
                style={{ borderColor: hidden ? undefined : def.color + "60" }}
              >
                <span className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle"
                  style={{ backgroundColor: hidden ? "#555" : def.color }} />
                {layer}
                <span className="text-white/40 ml-1">({count})</span>
              </button>
            );
          })}
      </div>

      {/* Stats */}
      <div className="absolute top-3 right-3 z-20 bg-black/60 backdrop-blur-sm rounded-xl px-3 py-2 border border-white/10">
        <p className="text-[10px] text-white/50">{nodes.length} nodes &middot; {links.length} edges</p>
      </div>

      <ForceGraph2D
        ref={fgRef}
        graphData={{ nodes, links }}
        width={dimensions.w}
        height={dimensions.h}
        backgroundColor="transparent"
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
          const linkCount = node.linkCount || 0;
          const size = 4 + (linkCount / (maxLinkCount || 1)) * 10;
          ctx.beginPath();
          ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
        linkCanvasObject={paintLink}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.8}
        cooldownTime={3000}
        cooldownTicks={0}
        onEngineStop={() => {
          if (!initializedRef.current) return;
          // zoomToFit solo al primo stop, poi mai più
          fgRef.current?.zoomToFit(300, 50);
          initializedRef.current = false;
        }}
        enableZoomInteraction={true}
        enablePanInteraction={true}
        enableNodeDrag={true}
        onNodeHover={(node: any) => setHoveredNode(node?.id || null)}
        onNodeClick={(node: any) => {
          if (fgRef.current && node) {
            fgRef.current.centerAt(node.x, node.y, 400);
            fgRef.current.zoom(3, 400);
          }
        }}
      />
    </div>
  );
}
