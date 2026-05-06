"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { X, Trash2, MessageSquare, Box, Network, Layers, Target, Cog } from "lucide-react";
import { useGraphStore, type GraphNode } from "@/lib/graph-store";

const LAYER_BADGE: Record<string, string> = {
  Strategy: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  Motivation: "bg-lime-500/15 text-lime-300 border-lime-500/30",
  Business: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  Application: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  Technology: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

function iconForLayer(layer: string) {
  switch (layer) {
    case "Strategy":
      return <Target className="w-3.5 h-3.5" />;
    case "Motivation":
      return <Layers className="w-3.5 h-3.5" />;
    case "Business":
      return <Network className="w-3.5 h-3.5" />;
    case "Application":
      return <Box className="w-3.5 h-3.5" />;
    case "Technology":
      return <Cog className="w-3.5 h-3.5" />;
    default:
      return <Box className="w-3.5 h-3.5" />;
  }
}

export default function SelectionDrawer() {
  const router = useRouter();
  const nodes = useGraphStore((s) => s.nodes);
  const selection = useGraphStore((s) => s.selection);
  const toggleSelect = useGraphStore((s) => s.toggleSelect);
  const clearSelection = useGraphStore((s) => s.clearSelection);
  const setScope = useGraphStore((s) => s.setScope);

  const selectedNodes: GraphNode[] = useMemo(() => {
    const ids = selection;
    return nodes.filter((n) => ids.has(n.id));
  }, [nodes, selection]);

  const useAsScope = () => {
    const ids = selectedNodes.map((n) => n.id);
    setScope(ids);
    router.push(`/chat?scope=${ids.join(",")}`);
  };

  return (
    <aside
      data-testid="selection-drawer"
      className="w-full h-full flex flex-col bg-slate-950/70 backdrop-blur-xl border-l border-white/10"
    >
      <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-white/50">
            Selection
          </p>
          <p className="text-sm font-semibold text-white/90">
            {selectedNodes.length} {selectedNodes.length === 1 ? "entity" : "entities"}
          </p>
        </div>
        {selectedNodes.length > 0 && (
          <button
            type="button"
            onClick={clearSelection}
            className="inline-flex items-center gap-1 text-[10px] text-white/60 hover:text-white px-2 py-1 rounded-md border border-white/10 hover:border-white/30 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            Clear all
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-2">
        {selectedNodes.length === 0 ? (
          <div className="text-center text-xs text-white/40 py-10 px-4">
            Shift-click nodes in the canvas to add them to your selection.
          </div>
        ) : (
          selectedNodes.map((n) => (
            <div
              key={n.id}
              className="group flex items-start gap-2 p-2.5 rounded-lg bg-white/[0.03] border border-white/10 hover:border-white/20 transition-colors"
            >
              <div className={`shrink-0 mt-0.5 p-1 rounded-md border ${LAYER_BADGE[n.layer] || "bg-white/5 text-white/60 border-white/10"}`}>
                {iconForLayer(n.layer)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-white/90 truncate">{n.name}</div>
                <div className="text-[10px] text-white/50 truncate">{n.type}</div>
                <span className={`mt-1 inline-block text-[9px] px-1.5 py-0.5 rounded border ${LAYER_BADGE[n.layer] || "bg-white/5 text-white/60 border-white/10"}`}>
                  {n.layer}
                </span>
              </div>
              <button
                type="button"
                aria-label={`Remove ${n.name}`}
                onClick={() => toggleSelect(n.id)}
                className="shrink-0 opacity-50 group-hover:opacity-100 p-1 rounded hover:bg-white/10 transition"
              >
                <X className="w-3.5 h-3.5 text-white/70" />
              </button>
            </div>
          ))
        )}
      </div>

      {selectedNodes.length > 0 && (
        <div className="border-t border-white/10 p-3">
          <button
            type="button"
            onClick={useAsScope}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white text-xs font-semibold transition-all shadow-lg shadow-orange-500/20"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Use {selectedNodes.length} {selectedNodes.length === 1 ? "entity" : "entities"} as chat scope
          </button>
        </div>
      )}
    </aside>
  );
}
