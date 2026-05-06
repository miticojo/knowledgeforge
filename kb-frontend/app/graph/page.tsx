"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Network, MessageSquare, PanelRightClose, PanelRightOpen } from "lucide-react";
import EmptyState from "@/components/EmptyState";
import { useGraphStore } from "@/lib/graph-store";
import GraphCanvas from "@/components/graph/GraphCanvas";
import SelectionDrawer from "@/components/graph/SelectionDrawer";
import GraphFilterSidebar from "@/components/graph/GraphFilterSidebar";
import GraphSearchBar from "@/components/graph/GraphSearchBar";

export default function GraphPage() {
  const router = useRouter();
  const setNodes = useGraphStore((s) => s.setNodes);
  const setEdges = useGraphStore((s) => s.setEdges);
  const setLoading = useGraphStore((s) => s.setLoading);
  const setError = useGraphStore((s) => s.setError);
  const setScope = useGraphStore((s) => s.setScope);
  const nodes = useGraphStore((s) => s.nodes);
  const selection = useGraphStore((s) => s.selection);
  const isLoading = useGraphStore((s) => s.isLoading);
  const error = useGraphStore((s) => s.error);

  const [drawerOpen, setDrawerOpen] = useState(true);
  const [hasFetched, setHasFetched] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(undefined);
      try {
        const res = await fetch("/api/graph/all?limit=500&offset=0");
        const data = await res.json();
        if (cancelled) return;
        // Normalize backend shape (entity_id) -> store shape (id)
        const rawNodes = Array.isArray(data?.nodes) ? data.nodes : [];
        const normalized = rawNodes.map((n: any) => ({
          id: n.id || n.entity_id,
          type: n.type,
          name: n.name,
          layer: n.layer,
        }));
        setNodes(normalized);
        setEdges(Array.isArray(data?.edges) ? data.edges : []);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load graph");
      } finally {
        if (!cancelled) {
          setLoading(false);
          setHasFetched(true);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [setNodes, setEdges, setLoading, setError]);

  const useSelectionAsScope = () => {
    const ids = Array.from(selection);
    setScope(ids);
    router.push(`/chat?scope=${ids.join(",")}`);
  };

  const showEmpty = hasFetched && !isLoading && !error && nodes.length === 0;

  return (
    <div className="flex flex-col h-screen w-full bg-slate-950 text-white overflow-hidden">
      {/* Top bar */}
      <header className="shrink-0 h-14 px-5 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-2 text-orange-400">
            <Network className="w-4 h-4" />
            <span className="text-sm font-bold tracking-tight">Graph</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-white/40">
            <ChevronRight className="w-3 h-3" />
            <span>Knowledge</span>
            <ChevronRight className="w-3 h-3" />
            <span className="text-white/70">Navigation</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[11px] text-white/50">
            {selection.size} selected
          </span>
          <button
            type="button"
            disabled={selection.size === 0}
            onClick={useSelectionAsScope}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 disabled:opacity-40 disabled:cursor-not-allowed text-white text-[11px] font-semibold transition-all"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Use {selection.size} as chat scope
          </button>
          <button
            type="button"
            aria-label={drawerOpen ? "Close drawer" : "Open drawer"}
            onClick={() => setDrawerOpen((v) => !v)}
            className="p-1.5 rounded-md hover:bg-white/10 transition"
          >
            {drawerOpen ? (
              <PanelRightClose className="w-4 h-4 text-white/70" />
            ) : (
              <PanelRightOpen className="w-4 h-4 text-white/70" />
            )}
          </button>
        </div>
      </header>

      <div className="flex-1 min-h-0 flex">
        {/* Left filter sidebar slot */}
        <div
          id="filter-sidebar-slot"
          data-testid="filter-sidebar-slot"
          className="w-[280px] shrink-0 border-r border-white/10 bg-slate-950/60 backdrop-blur-xl overflow-y-auto"
        >
          <GraphFilterSidebar />
        </div>

        {/* Main column */}
        <main className="flex-1 min-w-0 flex flex-col">
          <div
            id="graph-search-bar-slot"
            data-testid="graph-search-bar-slot"
            className="shrink-0 border-b border-white/10 bg-slate-950/60 p-2"
          >
            <GraphSearchBar />
          </div>
          <div className="flex-1 min-h-0 relative">
            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center text-xs text-white/50 z-10">
                Loading graph…
              </div>
            )}
            {error && (
              <div className="absolute inset-0 flex items-center justify-center text-xs text-red-400 z-10">
                {error}
              </div>
            )}
            {showEmpty ? (
              <EmptyState
                icon={<Network />}
                title="No graph data yet"
                body="Ingest a document to start building your knowledge graph."
                cta={{ label: "Go to Ingestion", href: "/ingestion" }}
              />
            ) : (
              <GraphCanvas />
            )}
          </div>
        </main>

        {/* Right drawer */}
        {drawerOpen && (
          <div className="w-[320px] shrink-0">
            <SelectionDrawer />
          </div>
        )}
      </div>
    </div>
  );
}
