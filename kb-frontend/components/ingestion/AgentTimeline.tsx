"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Database,
  GitBranch,
  Loader2,
  Network,
  Route,
  Workflow,
} from "lucide-react";
import {
  IngestEventsState,
  FileSummary,
  useIngestEvents,
} from "@/lib/use-ingest-events";
import { LAYER_COLORS, Layer } from "@/lib/archimate";
import RoutingBadge from "./RoutingBadge";

type Phase = "Acquisition" | "Routing" | "Parse" | "Map" | "Write";

const PHASE_ORDER: Phase[] = ["Acquisition", "Routing", "Parse", "Map", "Write"];

const PHASE_ICON: Record<Phase, React.ComponentType<{ className?: string }>> = {
  Acquisition: GitBranch,
  Routing: Route,
  Parse: Workflow,
  Map: Network,
  Write: Database,
};

const PHASE_LABEL: Record<Phase, string> = {
  Acquisition: "Acquisition",
  Routing: "Routing",
  Parse: "Parse",
  Map: "Map → ArchiMate",
  Write: "Write",
};

function derivePhases(state: IngestEventsState): Record<Phase, "idle" | "active" | "done"> {
  const phases: Record<Phase, "idle" | "active" | "done"> = {
    Acquisition: "idle",
    Routing: "idle",
    Parse: "idle",
    Map: "idle",
    Write: "idle",
  };

  if (state.status !== "idle") {
    phases.Acquisition = "done";
  }

  const hasRoute = state.events.some((e) => e.name === "route");
  const hasParseStart = state.events.some((e) => e.name === "parse_start");
  const hasParseEnd = state.events.some(
    (e) => e.name === "parse_end" || e.name === "parse_error"
  );
  const allParsed =
    hasParseStart &&
    state.fileSummaries.length > 0 &&
    state.fileSummaries.every((f) => f.status === "done" || f.status === "failed");

  if (hasRoute) phases.Routing = allParsed || hasParseStart ? "done" : "active";
  if (hasParseStart) phases.Parse = allParsed ? "done" : "active";
  // Heuristic: as soon as parse_end events arrive, mapping is happening implicitly
  // (per-file mapping into ArchiMate layers). Mark as active until write_start.
  if (hasParseEnd) phases.Map = state.writePhase !== "pending" ? "done" : "active";
  if (state.writePhase === "writing") phases.Write = "active";
  if (state.writePhase === "done") phases.Write = "done";

  if (state.status === "complete") {
    for (const p of PHASE_ORDER) phases[p] = "done";
  }

  return phases;
}

function formatMs(ms: number): string {
  if (!ms || ms < 0) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function ConfidenceBar({
  extracted,
  inferred,
  ambiguous,
}: {
  extracted: number;
  inferred: number;
  ambiguous: number;
}) {
  const total = Math.max(1, extracted + inferred + ambiguous);
  const e = (extracted / total) * 100;
  const i = (inferred / total) * 100;
  const a = (ambiguous / total) * 100;
  return (
    <div
      className="flex h-1.5 w-full overflow-hidden rounded-full bg-white/5"
      title={`EXTRACTED ${extracted} · INFERRED ${inferred} · AMBIGUOUS ${ambiguous}`}
      aria-label={`Confidence: ${extracted} extracted, ${inferred} inferred, ${ambiguous} ambiguous`}
    >
      <span style={{ width: `${e}%` }} className="bg-emerald-400" />
      <span style={{ width: `${i}%` }} className="bg-amber-400" />
      <span style={{ width: `${a}%` }} className="bg-red-400" />
    </div>
  );
}

function LayerChips({ breakdown }: { breakdown: Record<string, number> }) {
  const entries = Object.entries(breakdown).filter(([, n]) => n > 0);
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([layer, n]) => {
        const color = LAYER_COLORS[layer as Layer] ?? "#94a3b8";
        return (
          <span
            key={layer}
            className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold"
            style={{
              borderColor: `${color}55`,
              backgroundColor: `${color}1a`,
              color,
            }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            {layer} {n}
          </span>
        );
      })}
    </div>
  );
}

function FileRow({ summary }: { summary: FileSummary }) {
  const [open, setOpen] = useState(summary.status === "failed");
  const failed = summary.status === "failed";
  const parsing = summary.status === "parsing";
  const isDone = summary.status === "done";

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className={`group rounded-xl border transition-colors ${
        failed
          ? "border-red-500/50 bg-red-500/5"
          : isDone
          ? "border-white/10 bg-white/[0.03]"
          : "border-white/5 bg-white/[0.02]"
      }`}
    >
      <summary className="flex cursor-pointer list-none items-center gap-3 p-3 outline-none">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center">
          {failed ? (
            <AlertCircle className="h-4 w-4 text-red-400" />
          ) : parsing ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
          ) : isDone ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          ) : (
            <Activity className="h-4 w-4 text-white/40" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="truncate font-mono text-[11px] text-white/85"
              title={summary.file}
            >
              {summary.file}
            </span>
            <RoutingBadge parser={summary.parser} reason={summary.reason} />
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className="rounded-md border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] font-semibold text-white/70">
              {summary.entities} ent
            </span>
            <span className="rounded-md border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] font-semibold text-white/70">
              {summary.edges} edg
            </span>
            <span className="rounded-md border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] font-mono text-white/50">
              {formatMs(summary.duration_ms)}
            </span>
            <LayerChips breakdown={summary.layer_breakdown} />
          </div>

          <div className="mt-2">
            <ConfidenceBar
              extracted={summary.confidence_breakdown?.EXTRACTED ?? 0}
              inferred={summary.confidence_breakdown?.INFERRED ?? 0}
              ambiguous={summary.confidence_breakdown?.AMBIGUOUS ?? 0}
            />
          </div>
        </div>

        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-white/40 transition-transform group-open:rotate-180" />
      </summary>

      {(failed || summary.reason) && (
        <div className="space-y-2 px-3 pb-3 pt-0 text-[11px]">
          {summary.reason && (
            <div className="rounded-md border border-white/5 bg-black/30 p-2 text-white/60">
              <span className="text-[9px] font-bold uppercase tracking-wider text-white/40">
                Routing reason
              </span>
              <div className="mt-0.5">{summary.reason}</div>
            </div>
          )}
          {failed && summary.error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 font-mono text-red-200">
              {summary.error}
            </div>
          )}
        </div>
      )}
    </details>
  );
}

function StatusBadge({ status }: { status: IngestEventsState["status"] }) {
  if (status === "complete") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/40 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
        <CheckCircle2 className="h-3 w-3" /> Complete
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-red-400/40 bg-red-500/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-red-300">
        <AlertCircle className="h-3 w-3" /> Failed
      </span>
    );
  }
  if (status === "running") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-400/40 bg-blue-500/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-blue-300">
        <Loader2 className="h-3 w-3 animate-spin" /> Running
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white/50">
      Idle
    </span>
  );
}

export interface AgentTimelineProps {
  jobId?: string | null;
  /** Inject pre-built state for tests / Storybook. When provided the hook is skipped. */
  state?: IngestEventsState;
  /** Optional slot rendered in the header (e.g. "Show delta graph" toggle). */
  headerExtra?: React.ReactNode;
}

export default function AgentTimeline({ jobId, state, headerExtra }: AgentTimelineProps) {
  const liveState = useIngestEvents(state ? null : jobId ?? null);
  const view = state ?? liveState;
  const phases = useMemo(() => derivePhases(view), [view]);

  // Auto-scroll to newest, but pause when user scrolls up.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [autoscroll, setAutoscroll] = useState(true);

  useEffect(() => {
    if (!autoscroll) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [view.fileSummaries.length, view.events.length, autoscroll]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setAutoscroll(atBottom);
  };

  return (
    <section
      aria-label="Agent timeline"
      className="flex h-full min-h-0 flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="border-b border-[var(--card-border)] bg-[var(--background)]/70 px-5 py-4 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400">
            <Network className="h-4 w-4 text-blue-400" /> Agent Timeline
          </h3>
          <div className="flex items-center gap-2">
            {headerExtra}
            <StatusBadge status={view.status} />
          </div>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          <Counter label="Entities" value={view.totals.total_entities} />
          <Counter label="Edges" value={view.totals.total_edges} />
          <Counter label="Duration" value={formatMs(view.totals.duration_ms)} mono />
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {PHASE_ORDER.map((phase) => {
            const Icon = PHASE_ICON[phase];
            const s = phases[phase];
            const cls =
              s === "done"
                ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                : s === "active"
                ? "border-blue-400/50 bg-blue-500/10 text-blue-200 animate-pulse"
                : "border-white/10 bg-white/[0.02] text-white/40";
            return (
              <span
                key={phase}
                className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-semibold ${cls}`}
              >
                <Icon className="h-3 w-3" /> {PHASE_LABEL[phase]}
              </span>
            );
          })}
        </div>
      </div>

      {/* File list */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-4"
      >
        {view.fileSummaries.length === 0 ? (
          <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 text-center text-xs text-white/40">
            <Loader2 className="h-5 w-5 animate-spin text-blue-400/70" />
            Awaiting first routing event…
          </div>
        ) : (
          view.fileSummaries.map((f) => <FileRow key={f.file} summary={f} />)
        )}
      </div>

      {/* Footer summary */}
      <div className="border-t border-[var(--card-border)] bg-black/30 px-5 py-2.5">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-white/50">
          <span>
            {view.totals.files_processed} processed
            {view.totals.files_failed > 0 && (
              <span className="text-red-400"> · {view.totals.files_failed} failed</span>
            )}
          </span>
          <span className={autoscroll ? "text-white/40" : "text-amber-300"}>
            {autoscroll ? "Auto-scroll on" : "Auto-scroll paused"}
          </span>
        </div>
      </div>
    </section>
  );
}

function Counter({
  label,
  value,
  mono,
}: {
  label: string;
  value: number | string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/30 px-3 py-2">
      <div className="text-[9px] font-bold uppercase tracking-wider text-white/40">
        {label}
      </div>
      <div
        className={`mt-0.5 text-base font-bold text-white ${mono ? "font-mono" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}
