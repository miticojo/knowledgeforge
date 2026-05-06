"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, RefreshCw, Search } from "lucide-react";
import EmbeddingScatter, { type ProjectionPoint } from "@/components/embeddings/EmbeddingScatter";
import { useAuth } from "@/components/providers/AuthProvider";

interface ProjectionResponse {
  count: number;
  variance_explained: number[];
  points: ProjectionPoint[];
  projection_id: string | null;
  error?: string;
}

export default function EmbeddingsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [kind, setKind] = useState<"entities" | "chunks">("entities");
  const [data, setData] = useState<ProjectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [queryPoint, setQueryPoint] = useState<{ x: number; y: number; z: number } | null>(null);
  const [hits, setHits] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);

  const fetchProjection = async (refresh = false) => {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(
        `/api/embeddings/projection?kind=${kind}&limit=1500${refresh ? "&refresh=true" : ""}`,
        { headers: user?.email ? { "X-Tenant-Id": user.email } : undefined },
      );
      const json: ProjectionResponse = await res.json();
      if (json.error) setErr(json.error);
      setData(json);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjection();
    setQueryPoint(null);
    setHits([]);
  }, [kind]);

  const runQuery = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await fetch("/api/embeddings/nearest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(user?.email ? { "X-Tenant-Id": user.email } : {}),
        },
        body: JSON.stringify({ q: query, kind, top_k: 30 }),
      });
      const json = await res.json();
      if (json.query) setQueryPoint(json.query);
      const ids = (json.hits || []).map((h: any) => h.id);
      setHits(ids);
    } finally {
      setSearching(false);
    }
  };

  const variance = data?.variance_explained ?? [0, 0, 0];
  const totalVar = variance.reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-col h-screen bg-[var(--background)] text-[var(--foreground)]">
      <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--card-border)]">
        <div>
          <h1 className="text-xl font-semibold">Embedding Space</h1>
          <p className="text-xs opacity-60">3D PCA projection of stored vectors (768d → 3d)</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-[var(--card-bg)] border border-[var(--card-border)] rounded-lg overflow-hidden">
            {(["entities", "chunks"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={`px-3 py-1.5 text-sm capitalize transition-colors ${
                  kind === k ? "bg-blue-600 text-white" : "hover:bg-white/5"
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <button
            onClick={() => fetchProjection(true)}
            className="p-2 rounded-lg border border-[var(--card-border)] hover:bg-white/5"
            title="Recompute projection"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </header>

      <div className="flex items-center gap-2 px-6 py-3 border-b border-[var(--card-border)]">
        <Search className="w-4 h-4 opacity-60" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runQuery()}
          placeholder="Project a query into the same space..."
          className="flex-1 bg-transparent text-sm focus:outline-none"
        />
        <button
          onClick={runQuery}
          disabled={searching || !query.trim()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg disabled:opacity-50"
        >
          {searching ? "Projecting..." : "Project"}
        </button>
        {queryPoint && (
          <button
            onClick={() => {
              setQueryPoint(null);
              setHits([]);
              setQuery("");
            }}
            className="px-2 py-1.5 text-xs opacity-70 hover:opacity-100"
          >
            Clear
          </button>
        )}
      </div>

      <div className="px-6 py-2 text-xs opacity-70 border-b border-[var(--card-border)] flex gap-4">
        <span>{data?.count ?? 0} points</span>
        <span>
          variance explained: PC1 {(variance[0] * 100).toFixed(1)}% · PC2{" "}
          {(variance[1] * 100).toFixed(1)}% · PC3 {(variance[2] * 100).toFixed(1)}% (Σ{" "}
          {(totalVar * 100).toFixed(1)}%)
        </span>
        {err && <span className="text-red-400">{err}</span>}
      </div>

      <div className="flex-1 p-6">
        {loading && !data ? (
          <div className="flex items-center justify-center h-full opacity-60">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            Loading projection...
          </div>
        ) : data && data.points.length > 0 ? (
          <EmbeddingScatter
            points={data.points}
            query={queryPoint}
            highlightIds={hits}
            onSelect={(p) => {
              if (kind === "entities") router.push(`/graph?node=${p.id}`);
            }}
          />
        ) : (
          <div className="flex items-center justify-center h-full opacity-60 text-sm">
            No embeddings yet. Ingest some documents first.
          </div>
        )}
      </div>
    </div>
  );
}
