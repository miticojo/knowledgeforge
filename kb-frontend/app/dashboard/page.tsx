"use client";

import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";
import EmptyState from "@/components/EmptyState";

interface TenantCost {
  tenant_id: string;
  cost_usd: number;
  operations: number;
}

interface DailyPoint {
  day: string;
  cost_usd: number;
  operations: number;
}

interface OpBreakdown {
  op_type: string;
  cost_usd: number;
  operations: number;
}

interface DashboardData {
  tenant_id: string;
  top_tenants: TenantCost[];
  daily_trend: DailyPoint[];
  op_type_breakdown: OpBreakdown[];
}

function Sparkline({ data }: { data: DailyPoint[] }) {
  if (data.length === 0) {
    return <div className="text-sm text-[var(--foreground)]/40">No data</div>;
  }
  const W = 320;
  const H = 60;
  const max = Math.max(...data.map((d) => d.cost_usd), 0.0001);
  const step = data.length > 1 ? W / (data.length - 1) : 0;
  const points = data
    .map((d, i) => `${i * step},${H - (d.cost_usd / max) * H}`)
    .join(" ");
  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        points={points}
        className="text-blue-500"
      />
      {data.map((d, i) => (
        <circle
          key={d.day}
          cx={i * step}
          cy={H - (d.cost_usd / max) * H}
          r="3"
          className="fill-orange-500"
        >
          <title>{`${d.day}: $${d.cost_usd.toFixed(4)} (${d.operations} ops)`}</title>
        </circle>
      ))}
    </svg>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const tenantId = user?.email || "demo@local";
    fetch("/api/tenant-dashboard", {
      headers: { "X-Tenant-Id": tenantId },
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.error) setError(d.error);
        else setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [user]);

  if (loading) {
    return <div className="container mx-auto p-6">Loading dashboard...</div>;
  }
  if (error) {
    return (
      <div className="container mx-auto p-6 text-red-500">
        Error: {error}
      </div>
    );
  }
  if (!data) return null;

  if (data.top_tenants.length === 0 && data.daily_trend.length === 0) {
    return (
      <div className="container mx-auto p-6">
        <EmptyState
          icon={<BarChart3 />}
          title="No costs tracked yet"
          body="Run a query in the chat or ingest a document. Costs appear here within a few seconds."
          cta={{ label: "Open chat", href: "/chat" }}
        />
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold">Tenant Cost Dashboard</h1>
      <p className="text-sm text-[var(--foreground)]/60">
        Viewing as: <code>{data.tenant_id}</code>
      </p>

      <section>
        <h2 className="text-lg font-semibold mb-3">Daily Trend (last 7 days)</h2>
        <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-4">
          <Sparkline data={data.daily_trend} />
          <div className="text-xs text-[var(--foreground)]/40 mt-2">
            Hover points for daily totals.
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Top 10 Tenants (last 30 days)</h2>
        <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[var(--background)]/50">
              <tr>
                <th className="text-left p-2">Tenant</th>
                <th className="text-right p-2">Cost (USD)</th>
                <th className="text-right p-2">Operations</th>
              </tr>
            </thead>
            <tbody>
              {data.top_tenants.map((t) => (
                <tr key={t.tenant_id} className="border-t border-[var(--card-border)]">
                  <td className="p-2"><code>{t.tenant_id}</code></td>
                  <td className="p-2 text-right">${t.cost_usd.toFixed(4)}</td>
                  <td className="p-2 text-right">{t.operations}</td>
                </tr>
              ))}
              {data.top_tenants.length === 0 && (
                <tr><td colSpan={3} className="p-4 text-center text-[var(--foreground)]/40">No data</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Operation Breakdown ({data.tenant_id})</h2>
        <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[var(--background)]/50">
              <tr>
                <th className="text-left p-2">Op Type</th>
                <th className="text-right p-2">Cost (USD)</th>
                <th className="text-right p-2">Operations</th>
              </tr>
            </thead>
            <tbody>
              {data.op_type_breakdown.map((o) => (
                <tr key={o.op_type} className="border-t border-[var(--card-border)]">
                  <td className="p-2">{o.op_type}</td>
                  <td className="p-2 text-right">${o.cost_usd.toFixed(4)}</td>
                  <td className="p-2 text-right">{o.operations}</td>
                </tr>
              ))}
              {data.op_type_breakdown.length === 0 && (
                <tr><td colSpan={3} className="p-4 text-center text-[var(--foreground)]/40">No data</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
