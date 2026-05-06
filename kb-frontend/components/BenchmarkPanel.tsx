"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  FlaskConical,
  ChevronDown,
  ChevronRight,
  Search,
  Send,
  Clock,
  Target,
  CheckCircle2,
  XCircle,
  Info,
  BarChart3,
  Trophy,
  Minus,
  ArrowUp,
  ArrowDown,
  X,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface BenchmarkQuestion {
  id: string;
  question: string;
  gold_answer: string;
  type: "bridge" | "comparison";
  level: string;
  predicted_answer: string;
  em: number;
  f1: number;
  sp_recall: number;
  time_ms: number;
}

interface PaperBaseline {
  em: number;
  f1: number;
  r_at_2?: number;
  r_at_5?: number;
}

interface BenchmarkAggregates {
  avg_em: number;
  avg_f1: number;
  avg_sp_recall: number;
  by_type: {
    comparison: { em: number; f1: number; count: number };
    bridge: { em: number; f1: number; count: number };
  };
  total_questions: number;
  errors: number;
  avg_time_ms: number;
}

interface BenchmarkData {
  metadata: {
    dataset: string;
    source: string;
    n_questions: number;
    n_documents: number;
    difficulty: string;
    types: { bridge: number; comparison: number };
    date: string;
    pipeline: string;
  };
  aggregates: BenchmarkAggregates;
  paper_baselines: Record<string, PaperBaseline>;
  questions: BenchmarkQuestion[];
}

// ── Session tracking ─────────────────────────────────────────────────────────

interface SessionEntry {
  questionId: string;
  em: number;
  f1: number;
  sp_recall: number;
}

// ── Utility Components ───────────────────────────────────────────────────────

function KPIBadge({
  label,
  value,
  format,
  thresholds,
}: {
  label: string;
  value: number;
  format: "binary" | "percent";
  thresholds?: { good: number; medium: number };
}) {
  let colorClass: string;
  let displayValue: string;

  if (format === "binary") {
    colorClass = value === 1 ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" : "bg-red-500/15 text-red-400 border-red-500/25";
    displayValue = value === 1 ? "1" : "0";
  } else {
    const pct = value * 100;
    const t = thresholds ?? { good: 80, medium: 50 };
    colorClass =
      pct >= t.good
        ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
        : pct >= t.medium
        ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
        : "bg-red-500/15 text-red-400 border-red-500/25";
    displayValue = `${pct.toFixed(1)}%`;
  }

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold tabular-nums ${colorClass}`}>
      <span className="opacity-70 font-medium text-[10px] uppercase tracking-wide">{label}</span>
      {displayValue}
    </span>
  );
}

function MiniProgressBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="w-full h-1.5 rounded-full bg-slate-700/40 overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-700 ease-out ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function ComparisonDelta({ sessionVal, benchVal }: { sessionVal: number; benchVal: number }) {
  const delta = sessionVal - benchVal;
  if (Math.abs(delta) < 0.05) {
    return <Minus className="w-3 h-3 text-slate-500" />;
  }
  return delta > 0 ? (
    <span className="flex items-center gap-0.5 text-emerald-400 text-[10px] font-bold">
      <ArrowUp className="w-3 h-3" />+{delta.toFixed(1)}
    </span>
  ) : (
    <span className="flex items-center gap-0.5 text-red-400 text-[10px] font-bold">
      <ArrowDown className="w-3 h-3" />{delta.toFixed(1)}
    </span>
  );
}

// ── KPI Legend ────────────────────────────────────────────────────────────────

function KPILegend() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
      >
        <Info className="w-3 h-3" />
        <span>KPI Legend</span>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-2 z-50 w-72 p-3 rounded-xl border border-slate-700 bg-slate-900/95 backdrop-blur-xl shadow-2xl text-[11px] text-slate-300 space-y-2">
          <div className="flex justify-between items-start">
            <span className="font-bold text-xs text-slate-200">Metrics Legend</span>
            <button onClick={() => setOpen(false)} className="text-slate-500 hover:text-slate-300 cursor-pointer">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="space-y-1.5 pt-1">
            <p>
              <span className="font-semibold text-emerald-400">EM</span> = Exact Match: the predicted
              answer is exactly equal to the gold answer (0 or 1).
            </p>
            <p>
              <span className="font-semibold text-amber-400">F1</span> = F1 Score: token-level overlap
              between predicted and gold answer. Combines precision and recall in a single metric.
            </p>
            <p>
              <span className="font-semibold text-blue-400">SP Recall</span> = Supporting Facts
              Recall: percentage of gold documents (supporting facts) actually retrieved by the
              retrieval pipeline.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Session Summary Panel ────────────────────────────────────────────────────

function SessionSummary({
  session,
  aggregates,
}: {
  session: SessionEntry[];
  aggregates: BenchmarkAggregates;
}) {
  if (session.length === 0) return null;

  const avgEm = (session.reduce((s, e) => s + e.em, 0) / session.length) * 100;
  const avgF1 = (session.reduce((s, e) => s + e.f1, 0) / session.length) * 100;
  const avgSp = (session.reduce((s, e) => s + e.sp_recall, 0) / session.length) * 100;

  const rows = [
    { label: "EM", session: avgEm, bench: aggregates.avg_em, color: "bg-emerald-500" },
    { label: "F1", session: avgF1, bench: aggregates.avg_f1, color: "bg-amber-500" },
    { label: "SP Recall", session: avgSp, bench: aggregates.avg_sp_recall, color: "bg-blue-500" },
  ];

  return (
    <div className="mt-3 p-3 rounded-xl border border-slate-700/60 bg-slate-800/40 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-[10px] uppercase tracking-widest font-bold text-slate-400 flex items-center gap-1.5">
          <BarChart3 className="w-3 h-3" /> Session Summary ({session.length} questions)
        </h4>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {rows.map((r) => (
          <div key={r.label} className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold text-slate-400">{r.label}</span>
              <ComparisonDelta sessionVal={r.session} benchVal={r.bench} />
            </div>
            <div className="text-sm font-bold tabular-nums text-slate-200">{r.session.toFixed(1)}%</div>
            <MiniProgressBar value={r.session} max={100} color={r.color} />
            <div className="text-[9px] text-slate-500 tabular-nums">
              Benchmark: {r.bench.toFixed(1)}%
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export function BenchmarkPanel({
  onSendQuestion,
  isLoading,
}: {
  onSendQuestion: (question: string) => void;
  isLoading: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState<BenchmarkData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [session, setSession] = useState<SessionEntry[]>([]);
  const [typeFilter, setTypeFilter] = useState<"all" | "bridge" | "comparison">("all");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Load benchmark data
  useEffect(() => {
    fetch("/benchmark_hotpotqa.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: BenchmarkData) => setData(d))
      .catch((e) => setLoadError(e.message));
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filteredQuestions = useMemo(() => {
    if (!data) return [];
    let qs = data.questions;
    if (typeFilter !== "all") {
      qs = qs.filter((q) => q.type === typeFilter);
    }
    if (searchQuery.trim()) {
      const lower = searchQuery.toLowerCase();
      qs = qs.filter(
        (q) =>
          q.question.toLowerCase().includes(lower) ||
          q.gold_answer.toLowerCase().includes(lower)
      );
    }
    return qs;
  }, [data, searchQuery, typeFilter]);

  const selectedQuestion = useMemo(
    () => data?.questions.find((q) => q.id === selectedId) ?? null,
    [data, selectedId]
  );

  const handleSend = useCallback(() => {
    if (!selectedQuestion || isLoading) return;
    onSendQuestion(selectedQuestion.question);
    // Track in session
    setSession((prev) => {
      if (prev.some((e) => e.questionId === selectedQuestion.id)) return prev;
      return [
        ...prev,
        {
          questionId: selectedQuestion.id,
          em: selectedQuestion.em,
          f1: selectedQuestion.f1,
          sp_recall: selectedQuestion.sp_recall,
        },
      ];
    });
  }, [selectedQuestion, isLoading, onSendQuestion]);

  if (loadError) return null;
  if (!data) return null;

  return (
    <div className="border border-slate-700/50 rounded-2xl overflow-hidden bg-slate-900/50 backdrop-blur-sm transition-all duration-300">
      {/* Toggle Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 cursor-pointer group transition-colors hover:bg-slate-800/40"
      >
        <div className="p-1.5 rounded-lg bg-orange-500/10 border border-orange-500/20 text-orange-400 group-hover:bg-orange-500/20 transition-colors">
          <FlaskConical className="w-4 h-4" />
        </div>
        <div className="flex-1 text-left">
          <span className="text-sm font-semibold text-slate-200">Benchmark HotpotQA</span>
          <span className="ml-2 text-[10px] text-slate-500 tabular-nums">
            ({data.aggregates.total_questions} questions)
          </span>
        </div>
        {/* Aggregate badges */}
        <div className="hidden sm:flex items-center gap-2">
          <span className="text-[10px] tabular-nums px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            EM {data.aggregates.avg_em}%
          </span>
          <span className="text-[10px] tabular-nums px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-400 border border-amber-500/20">
            F1 {data.aggregates.avg_f1}%
          </span>
          <span className="text-[10px] tabular-nums px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20">
            SP {data.aggregates.avg_sp_recall}%
          </span>
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-500 shrink-0" />
        )}
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-4 pb-4 pt-1 space-y-3 border-t border-slate-700/50">
          {/* Pipeline info */}
          <div className="text-[10px] text-slate-500 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>Pipeline: <span className="text-slate-400">{data.metadata.pipeline}</span></span>
            <span>Date: <span className="text-slate-400">{data.metadata.date}</span></span>
            <span>Documents: <span className="text-slate-400 tabular-nums">{data.metadata.n_documents}</span></span>
            <span>Avg time: <span className="text-slate-400 tabular-nums">{(data.aggregates.avg_time_ms / 1000).toFixed(1)}s</span></span>
          </div>

          {/* Paper baselines comparison row */}
          <div className="flex flex-wrap items-center gap-2">
            <Trophy className="w-3.5 h-3.5 text-amber-500/70 shrink-0" />
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">vs Baselines:</span>
            {Object.entries(data.paper_baselines).map(([name, b]) => (
              <span
                key={name}
                className="text-[9px] tabular-nums px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-slate-400"
                title={`${name}: EM=${b.em}, F1=${b.f1}`}
              >
                {name} <span className="text-slate-500">EM</span> {b.em} <span className="text-slate-500">F1</span> {b.f1}
              </span>
            ))}
          </div>

          {/* Type filter + Search */}
          <div className="flex flex-col sm:flex-row gap-2">
            {/* Type filter buttons */}
            <div className="flex gap-1 shrink-0">
              {(["all", "bridge", "comparison"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => { setTypeFilter(t); setSelectedId(null); }}
                  className={`px-2.5 py-1 rounded-lg text-[10px] font-semibold uppercase tracking-wide border transition-colors cursor-pointer ${
                    typeFilter === t
                      ? "bg-orange-500/15 text-orange-400 border-orange-500/30"
                      : "bg-slate-800/60 text-slate-500 border-slate-700/40 hover:text-slate-300 hover:border-slate-600"
                  }`}
                >
                  {t === "all" ? `All (${data.aggregates.total_questions})` : `${t} (${data.aggregates.by_type[t].count})`}
                </button>
              ))}
            </div>

            {/* Searchable dropdown */}
            <div className="flex-1 relative" ref={dropdownRef}>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
                <input
                  ref={searchInputRef}
                  type="text"
                  placeholder="Search benchmark questions..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setDropdownOpen(true);
                  }}
                  onFocus={() => setDropdownOpen(true)}
                  className="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-800/60 border border-slate-700/50 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-orange-500/40 focus:ring-1 focus:ring-orange-500/20 transition-all"
                />
                {searchQuery && (
                  <button
                    onClick={() => { setSearchQuery(""); searchInputRef.current?.focus(); }}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Dropdown list */}
              {dropdownOpen && (
                <div className="absolute z-50 mt-1 w-full max-h-64 overflow-y-auto rounded-xl border border-slate-700 bg-slate-900/98 backdrop-blur-xl shadow-2xl">
                  {filteredQuestions.length === 0 ? (
                    <div className="px-4 py-3 text-xs text-slate-500">No results</div>
                  ) : (
                    filteredQuestions.map((q) => (
                      <button
                        key={q.id}
                        onClick={() => {
                          setSelectedId(q.id);
                          setDropdownOpen(false);
                          setSearchQuery("");
                        }}
                        className={`w-full text-left px-4 py-2.5 flex items-start gap-2 border-b border-slate-800/50 last:border-0 transition-colors cursor-pointer ${
                          selectedId === q.id
                            ? "bg-orange-500/10"
                            : "hover:bg-slate-800/60"
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <span className="text-xs text-slate-200 line-clamp-2 leading-relaxed">
                            {q.question}
                          </span>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-[9px] uppercase font-bold tracking-wider ${
                              q.type === "comparison" ? "text-purple-400" : "text-cyan-400"
                            }`}>
                              {q.type}
                            </span>
                            {q.em === 1 ? (
                              <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                            ) : (
                              <XCircle className="w-3 h-3 text-red-500/60" />
                            )}
                            <span className="text-[9px] text-slate-500 tabular-nums">
                              F1 {(q.f1 * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Selected question detail card */}
          {selectedQuestion && (
            <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 overflow-hidden">
              {/* Question */}
              <div className="p-4 space-y-3">
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className={`text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md border ${
                      selectedQuestion.type === "comparison"
                        ? "text-purple-400 bg-purple-500/10 border-purple-500/20"
                        : "text-cyan-400 bg-cyan-500/10 border-cyan-500/20"
                    }`}>
                      {selectedQuestion.type}
                    </span>
                    <span className="text-[9px] text-slate-500 font-mono">{selectedQuestion.id.slice(0, 8)}</span>
                  </div>
                  <p className="text-sm font-medium text-slate-100 leading-relaxed">
                    {selectedQuestion.question}
                  </p>
                </div>

                {/* Answers comparison */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/15">
                    <span className="text-[9px] uppercase tracking-wider font-bold text-emerald-500/70 block mb-1">
                      <Target className="w-3 h-3 inline mr-1" />
                      Expected answer
                    </span>
                    <p className="text-xs text-slate-200 font-medium">{selectedQuestion.gold_answer}</p>
                  </div>
                  <div className={`p-2.5 rounded-lg border ${
                    selectedQuestion.em === 1
                      ? "bg-emerald-500/5 border-emerald-500/15"
                      : "bg-slate-800/40 border-slate-700/40"
                  }`}>
                    <span className={`text-[9px] uppercase tracking-wider font-bold block mb-1 ${
                      selectedQuestion.em === 1 ? "text-emerald-500/70" : "text-slate-500"
                    }`}>
                      System answer
                    </span>
                    <p className="text-xs text-slate-200 font-medium">{selectedQuestion.predicted_answer}</p>
                  </div>
                </div>

                {/* KPI Badges row */}
                <div className="flex flex-wrap items-center gap-2">
                  <KPIBadge label="EM" value={selectedQuestion.em} format="binary" />
                  <KPIBadge label="F1" value={selectedQuestion.f1} format="percent" />
                  <KPIBadge
                    label="SP Recall"
                    value={selectedQuestion.sp_recall}
                    format="percent"
                    thresholds={{ good: 90, medium: 50 }}
                  />
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-700/40 bg-slate-800/40 text-xs text-slate-400 tabular-nums">
                    <Clock className="w-3 h-3 opacity-60" />
                    {(selectedQuestion.time_ms / 1000).toFixed(1)}s
                  </span>
                </div>
              </div>

              {/* Send button */}
              <div className="px-4 py-3 border-t border-slate-700/40 bg-slate-800/20 flex items-center justify-between gap-3">
                <KPILegend />
                <button
                  onClick={handleSend}
                  disabled={isLoading}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                    isLoading
                      ? "opacity-40 cursor-not-allowed bg-slate-700 text-slate-400"
                      : "bg-orange-500 text-white hover:bg-orange-600 active:scale-[0.97] shadow-lg shadow-orange-500/20"
                  }`}
                >
                  <Send className="w-3.5 h-3.5" />
                  Send to Chat
                </button>
              </div>
            </div>
          )}

          {/* Session Summary */}
          <SessionSummary session={session} aggregates={data.aggregates} />
        </div>
      )}
    </div>
  );
}
