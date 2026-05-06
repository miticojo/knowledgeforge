"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { Database, Share2, Loader2, DollarSign } from "lucide-react";

interface TenantStatsData {
  documents: number;
  chunks: number;
  shared_documents: number;
  shared_chunks: number;
}

interface TenantCostsData {
  total_cost: number;
  ingestion_cost: number;
  query_cost: number;
  total_tokens: number;
}

function parseCosts(data: any): TenantCostsData | null {
  try {
    const allTime = data?.all_time;
    if (!allTime) return null;
    const ingestion = allTime.ingestion || {};
    const query = allTime.query || {};
    return {
      total_cost: allTime.total_cost_usd || 0,
      ingestion_cost: ingestion.cost_usd || 0,
      query_cost: query.cost_usd || 0,
      total_tokens: (ingestion.input_tokens || 0) + (ingestion.output_tokens || 0)
        + (query.input_tokens || 0) + (query.output_tokens || 0),
    };
  } catch {
    return null;
  }
}

const POLL_INTERVAL_MS = 30_000;

export function TenantStats() {
  const { user } = useAuth();
  const [stats, setStats] = useState<TenantStatsData | null>(null);
  const [costs, setCosts] = useState<TenantCostsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchStats = useCallback(async () => {
    if (!user?.email) return;
    try {
      const [statsRes, costsRes] = await Promise.all([
        fetch("/api/tenant-stats", {
          headers: { "X-Tenant-Id": user.email },
        }),
        fetch("/api/tenant-costs", {
          headers: { "X-Tenant-Id": user.email },
        }),
      ]);
      if (!statsRes.ok) throw new Error();
      const statsData = await statsRes.json();
      setStats(statsData);
      // Costs are optional -- don't fail the whole component if unavailable
      if (costsRes.ok) {
        const costsData = await costsRes.json();
        setCosts(parseCosts(costsData));
      }
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [user?.email]);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchStats]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl border border-[var(--card-border)] bg-black/5 dark:bg-white/5">
        <Loader2 className="w-3 h-3 animate-spin opacity-40" />
        <span className="text-[10px] opacity-40">Loading stats...</span>
      </div>
    );
  }

  if (error || !stats) return null;

  return (
    <div className="flex flex-wrap items-center gap-3 px-3 py-2.5 rounded-xl border border-[var(--card-border)] bg-black/5 dark:bg-white/5">
      <div className="flex items-center gap-1.5">
        <Database className="w-3 h-3 text-orange-400 shrink-0" />
        <span className="text-[10px] font-semibold text-[var(--foreground)]">
          {stats.documents}
        </span>
        <span className="text-[10px] opacity-50">docs</span>
        <span className="text-[9px] opacity-30 tabular-nums">
          ({stats.chunks.toLocaleString()} chunks)
        </span>
      </div>

      <div className="w-px h-3 bg-[var(--card-border)]" />

      <div className="flex items-center gap-1.5">
        <Share2 className="w-3 h-3 text-blue-400 shrink-0" />
        <span className="text-[10px] font-semibold text-[var(--foreground)]">
          {stats.shared_documents}
        </span>
        <span className="text-[10px] opacity-50">shared</span>
        <span className="text-[9px] opacity-30 tabular-nums">
          ({stats.shared_chunks.toLocaleString()} chunks)
        </span>
      </div>

      {costs && (
        <>
          <div className="w-px h-3 bg-[var(--card-border)]" />

          <div className="flex items-center gap-1.5">
            <DollarSign className="w-3 h-3 text-emerald-400 shrink-0" />
            <span className="text-[10px] font-semibold text-[var(--foreground)]">
              ${costs.total_cost.toFixed(2)}
            </span>
            <span className="text-[9px] opacity-30 tabular-nums">
              ${costs.ingestion_cost.toFixed(2)} ingestion
            </span>
            <span className="text-[9px] opacity-30 tabular-nums">
              ${costs.query_cost.toFixed(2)} queries
            </span>
            <span className="text-[9px] opacity-30 tabular-nums">
              {formatTokens(costs.total_tokens)} tokens
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toString();
}
