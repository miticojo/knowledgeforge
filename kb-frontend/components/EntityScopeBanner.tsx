"use client";

import { useRouter } from "next/navigation";
import { Telescope, X, Network } from "lucide-react";
import { useGraphStore } from "@/lib/graph-store";

export function EntityScopeBanner() {
  const router = useRouter();
  const scope = useGraphStore((s) => s.scope);
  const clearScope = useGraphStore((s) => s.clearScope);

  if (scope.length === 0) return null;

  // TODO: fetch entity names via /api/graph/entities/by-ids?ids=... when endpoint exists.
  const label = `Filtered to ${scope.length} ${scope.length === 1 ? "entity" : "entities"}`;
  const graphHref = `/graph?selected=${scope.join(",")}`;

  return (
    <div
      role="status"
      aria-label="Entity scope filter active"
      className="mx-4 mb-2 flex items-center gap-3 px-3 py-2 rounded-full border border-orange-500/30 bg-gradient-to-r from-orange-500/10 via-orange-400/5 to-transparent text-orange-500 dark:text-orange-300 backdrop-blur-sm"
    >
      <Telescope className="w-4 h-4 shrink-0" aria-hidden="true" />
      <span className="text-xs font-semibold tracking-wide truncate">{label}</span>

      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => router.push(graphHref)}
          className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider border border-orange-500/30 hover:bg-orange-500/10 transition-colors cursor-pointer"
        >
          <Network className="w-3 h-3" />
          View graph
        </button>
        <button
          type="button"
          onClick={clearScope}
          aria-label="Clear scope"
          className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider border border-transparent hover:border-orange-500/30 hover:bg-orange-500/10 transition-colors cursor-pointer"
        >
          <X className="w-3 h-3" />
          Clear
        </button>
      </div>
    </div>
  );
}

export default EntityScopeBanner;
