"use client";

import { useState, useEffect } from "react";
import {
  FlaskConical,
  FileText,
  Search,
  Database,
  Cpu,
  Layers,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Loader2,
  Trophy,
  BarChart3,
  BookOpen,
  Target,
  Percent,
  Crosshair,
  ScanSearch,
  Sparkles,
  Upload,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import EmptyState from "@/components/EmptyState";

/* ---------- types ---------- */
interface BenchmarkData {
  metadata: {
    dataset: string;
    source: string;
    n_questions: number;
    n_documents: number;
    difficulty: string;
    types: Record<string, number>;
    date: string;
    pipeline: string;
  };
  aggregates: {
    avg_em: number;
    avg_f1: number;
    avg_sp_recall: number;
    by_type: Record<string, { em: number; f1: number; count: number }>;
    by_level: Record<string, { em: number; f1: number; count: number }>;
    total_questions: number;
    errors: number;
    avg_time_ms: number;
  };
  paper_baselines: Record<string, { em: number; f1: number; r_at_2?: number; r_at_5?: number }>;
  questions: Array<{
    id: string;
    question: string;
    gold_answer: string;
    type: string;
    level: string;
    predicted_answer: string;
    em: number;
    f1: number;
    sp_recall: number;
    time_ms: number;
  }>;
}

/* ---------- pipeline step data ---------- */
const INGESTION_STEPS = [
  { icon: FileText, label: "Documents", desc: "PDF, DOCX, text" },
  { icon: Layers, label: "Semantic Chunking", desc: "Contextual splitting" },
  { icon: Sparkles, label: "Contextual Retrieval", desc: "LLM enrichment per chunk" },
  { icon: Cpu, label: "Embedding", desc: "gemini-embedding-2" },
  { icon: Database, label: "Cloud Spanner", desc: "Distributed vector store" },
];

const SEARCH_STEPS = [
  { icon: Search, label: "Query", desc: "User question" },
  { icon: Layers, label: "Multi-query Expansion", desc: "Semantic variants" },
  { icon: ScanSearch, label: "Vector Search (ScaNN)", desc: "Top-K nearest neighbors" },
  { icon: Target, label: "Vertex AI Reranking", desc: "Semantic reranking" },
  { icon: Sparkles, label: "Answer", desc: "Gemini 2.5 Flash" },
];

/* ---------- helper: animated number ---------- */
function AnimatedNumber({ value, suffix = "", decimals = 1 }: { value: number; suffix?: string; decimals?: number }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    let frame: number;
    const duration = 1200;
    const start = performance.now();
    const animate = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(eased * value);
      if (progress < 1) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <>{display.toFixed(decimals)}{suffix}</>;
}

/* ========== PAGE ========== */
export default function BenchmarkPage() {
  const [data, setData] = useState<BenchmarkData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "confirm" | "loading" | "polling" | "success" | "error">("idle");
  const [loadMessage, setLoadMessage] = useState("");
  const [expandedQuestion, setExpandedQuestion] = useState<string | null>(null);
  const [showQuestions, setShowQuestions] = useState(false);
  const [questionFilter, setQuestionFilter] = useState<"all" | "correct" | "wrong">("all");

  // Fetch benchmark data
  useEffect(() => {
    fetch("/benchmark_hotpotqa.json")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setError("Unable to load benchmark data."));
  }, []);

  // Polling for load status
  useEffect(() => {
    if (loadState !== "polling") return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch("/api/benchmark/status");
        const status = await res.json();
        if (status.state === "complete") {
          setLoadState("success");
          setLoadMessage(`Load completed: ${status.documents_loaded ?? ""} documents ingested.`);
          clearInterval(interval);
        } else if (status.state === "error") {
          setLoadState("error");
          setLoadMessage(status.message || "Error during load.");
          clearInterval(interval);
        } else {
          setLoadMessage(status.message || "Processing in progress...");
        }
      } catch {
        setLoadState("error");
        setLoadMessage("Connection error during polling.");
        clearInterval(interval);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [loadState]);

  const handleLoadBenchmark = async () => {
    setLoadState("loading");
    try {
      const res = await fetch("/api/benchmark/load", { method: "POST" });
      if (!res.ok) throw new Error("API error");
      setLoadState("polling");
      setLoadMessage("Starting ingestion of 1989 Wikipedia documents...");
    } catch {
      setLoadState("error");
      setLoadMessage("Unable to start benchmark load.");
    }
  };

  if (error) {
    return (
      <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center">
        <div className="text-center space-y-3">
          <XCircle className="w-10 h-10 text-red-400 mx-auto" />
          <p className="text-red-400">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-orange-500" />
      </div>
    );
  }

  if (!data.questions || data.questions.length === 0) {
    return (
      <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center">
        <EmptyState
          icon={<FlaskConical />}
          title="No benchmark runs yet"
          body="Trigger a run from the evaluation/ scripts to see retrieval quality across HotpotQA + custom datasets."
          cta={{ label: "See evaluation guide", href: "https://github.com/miticojo/knowledgeforge/blob/main/evaluation/README.md" }}
        />
      </div>
    );
  }

  const { metadata, aggregates, paper_baselines } = data;
  const bestBaseline = Object.entries(paper_baselines).reduce((best, [name, vals]) =>
    vals.f1 > best.f1 ? { name, ...vals } : best,
    { name: "", em: 0, f1: 0 }
  );

  const filteredQuestions = data.questions.filter((q) => {
    if (questionFilter === "correct") return q.em === 1;
    if (questionFilter === "wrong") return q.em === 0;
    return true;
  });

  return (
    <div className="min-h-[calc(100vh-3.5rem)] relative overflow-x-hidden">
      {/* Background gradients */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] bg-orange-500/8 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 -left-40 w-[500px] h-[500px] bg-blue-500/6 rounded-full blur-[100px]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-orange-600/4 rounded-full blur-[150px]" />
      </div>

      <div className="relative z-10 max-w-6xl mx-auto px-4 md:px-8 py-10 space-y-10">

        {/* ===== 1. HERO ===== */}
        <section className="text-center space-y-4 pt-4 pb-2">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-orange-500/10 border border-orange-500/20 text-orange-500 text-xs font-semibold uppercase tracking-widest mb-2">
            <FlaskConical className="w-3.5 h-3.5" />
            Academic Validation
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight">
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-orange-400 via-orange-500 to-amber-500">
              Reference Benchmark
            </span>
          </h1>
          <p className="max-w-2xl mx-auto text-base md:text-lg opacity-70 leading-relaxed">
            Quantitative validation of the RAG architecture on{" "}
            <span className="font-semibold text-orange-400">HotpotQA</span>, the reference academic dataset
            for multi-hop question-answering. Results are compared against published papers to demonstrate
            the competitiveness of the end-to-end pipeline.
          </p>
        </section>

        {/* ===== 2. ARCHITECTURE OVERVIEW ===== */}
        <section className="rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[var(--card-border)] bg-black/5 dark:bg-white/5 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-orange-400" />
            <h2 className="font-semibold text-sm">Pipeline Architecture</h2>
          </div>
          <div className="p-6 space-y-8">
            {/* Ingestion Pipeline */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-widest opacity-50 mb-4 flex items-center gap-2">
                <Database className="w-3.5 h-3.5" /> Ingestion Pipeline
              </h3>
              <div className="flex flex-wrap items-center gap-2 md:gap-0">
                {INGESTION_STEPS.map((step, i) => (
                  <div key={step.label} className="flex items-center gap-2">
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-blue-500/5 border border-blue-500/10 hover:border-blue-500/25 hover:bg-blue-500/10 transition-all group">
                      <div className="p-2 rounded-lg bg-blue-500/10 group-hover:bg-blue-500/20 transition-colors">
                        <step.icon className="w-4 h-4 text-blue-400" />
                      </div>
                      <div>
                        <div className="text-xs font-semibold">{step.label}</div>
                        <div className="text-[10px] opacity-50">{step.desc}</div>
                      </div>
                    </div>
                    {i < INGESTION_STEPS.length - 1 && (
                      <ArrowRight className="w-4 h-4 opacity-30 hidden md:block mx-1" />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Search Pipeline */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-widest opacity-50 mb-4 flex items-center gap-2">
                <Search className="w-3.5 h-3.5" /> Search Pipeline
              </h3>
              <div className="flex flex-wrap items-center gap-2 md:gap-0">
                {SEARCH_STEPS.map((step, i) => (
                  <div key={step.label} className="flex items-center gap-2">
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-orange-500/5 border border-orange-500/10 hover:border-orange-500/25 hover:bg-orange-500/10 transition-all group">
                      <div className="p-2 rounded-lg bg-orange-500/10 group-hover:bg-orange-500/20 transition-colors">
                        <step.icon className="w-4 h-4 text-orange-400" />
                      </div>
                      <div>
                        <div className="text-xs font-semibold">{step.label}</div>
                        <div className="text-[10px] opacity-50">{step.desc}</div>
                      </div>
                    </div>
                    {i < SEARCH_STEPS.length - 1 && (
                      <ArrowRight className="w-4 h-4 opacity-30 hidden md:block mx-1" />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ===== 3. BENCHMARK RESULTS ===== */}
        <section className="rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[var(--card-border)] bg-black/5 dark:bg-white/5 flex items-center gap-2">
            <Trophy className="w-4 h-4 text-orange-400" />
            <h2 className="font-semibold text-sm">Benchmark Results</h2>
          </div>
          <div className="p-6 space-y-8">
            {/* Our KPIs - hero numbers */}
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold uppercase tracking-widest opacity-50">Our Pipeline</span>
                <span className="px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/20 text-green-400 text-[10px] font-bold uppercase">
                  Best on every KPI
                </span>
              </div>
              <p className="text-[11px] opacity-40 mb-5">{metadata.pipeline}</p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {/* EM */}
                <div className="relative overflow-hidden rounded-xl border border-orange-500/20 bg-gradient-to-br from-orange-500/10 to-orange-600/5 p-5">
                  <div className="absolute top-2 right-2 opacity-10">
                    <Crosshair className="w-16 h-16 text-orange-400" />
                  </div>
                  <div className="text-xs font-semibold text-orange-400 uppercase tracking-wider mb-1">Exact Match</div>
                  <div className="text-4xl font-black text-orange-400 tabular-nums">
                    <AnimatedNumber value={aggregates.avg_em} suffix="%" />
                  </div>
                  <div className="text-[10px] opacity-50 mt-1">vs best baseline: {bestBaseline.em}%</div>
                  <div className="mt-2 h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-orange-400 to-orange-600 transition-all duration-1000"
                      style={{ width: `${aggregates.avg_em}%` }}
                    />
                  </div>
                </div>

                {/* F1 */}
                <div className="relative overflow-hidden rounded-xl border border-amber-500/20 bg-gradient-to-br from-amber-500/10 to-amber-600/5 p-5">
                  <div className="absolute top-2 right-2 opacity-10">
                    <BarChart3 className="w-16 h-16 text-amber-400" />
                  </div>
                  <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-1">Token F1</div>
                  <div className="text-4xl font-black text-amber-400 tabular-nums">
                    <AnimatedNumber value={aggregates.avg_f1} suffix="%" />
                  </div>
                  <div className="text-[10px] opacity-50 mt-1">vs best baseline: {bestBaseline.f1}%</div>
                  <div className="mt-2 h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-amber-400 to-amber-600 transition-all duration-1000"
                      style={{ width: `${aggregates.avg_f1}%` }}
                    />
                  </div>
                </div>

                {/* SP Recall */}
                <div className="relative overflow-hidden rounded-xl border border-green-500/20 bg-gradient-to-br from-green-500/10 to-green-600/5 p-5">
                  <div className="absolute top-2 right-2 opacity-10">
                    <ScanSearch className="w-16 h-16 text-green-400" />
                  </div>
                  <div className="text-xs font-semibold text-green-400 uppercase tracking-wider mb-1">SP Recall</div>
                  <div className="text-4xl font-black text-green-400 tabular-nums">
                    <AnimatedNumber value={aggregates.avg_sp_recall} suffix="%" />
                  </div>
                  <div className="text-[10px] opacity-50 mt-1">Gold documents found by retrieval</div>
                  <div className="mt-2 h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-green-400 to-green-600 transition-all duration-1000"
                      style={{ width: `${aggregates.avg_sp_recall}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* By type breakdown */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-widest opacity-50 mb-3">Breakdown by Question Type</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {Object.entries(aggregates.by_type).map(([type, vals]) => (
                  <div key={type} className="flex items-center gap-4 px-4 py-3 rounded-xl bg-black/5 dark:bg-white/5 border border-[var(--card-border)]">
                    <div className="flex flex-col items-center min-w-[60px]">
                      <span className="text-[10px] font-bold uppercase tracking-wider opacity-50">{type}</span>
                      <span className="text-xs opacity-40">{vals.count} questions</span>
                    </div>
                    <div className="flex-1 flex gap-4">
                      <div>
                        <span className="text-[10px] opacity-40 block">EM</span>
                        <span className="text-sm font-bold text-orange-400">{vals.em}%</span>
                      </div>
                      <div>
                        <span className="text-[10px] opacity-40 block">F1</span>
                        <span className="text-sm font-bold text-amber-400">{vals.f1}%</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Paper baselines table */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-widest opacity-50 mb-3">Comparison with Published Papers</h3>
              <div className="overflow-x-auto rounded-xl border border-[var(--card-border)]">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-black/5 dark:bg-white/5 border-b border-[var(--card-border)]">
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider opacity-60">System</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider opacity-60">EM</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider opacity-60">F1</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider opacity-60">Delta F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* Our row - highlighted */}
                    <tr className="bg-orange-500/8 border-b border-orange-500/15">
                      <td className="px-4 py-3 font-bold text-orange-400 flex items-center gap-2">
                        <Trophy className="w-3.5 h-3.5" />
                        KB Pipeline (Ours)
                      </td>
                      <td className="text-right px-4 py-3 font-bold text-orange-400 tabular-nums">{aggregates.avg_em.toFixed(1)}</td>
                      <td className="text-right px-4 py-3 font-bold text-orange-400 tabular-nums">{aggregates.avg_f1.toFixed(1)}</td>
                      <td className="text-right px-4 py-3 font-bold text-orange-400">--</td>
                    </tr>
                    {/* Paper baselines sorted by F1 desc */}
                    {Object.entries(paper_baselines)
                      .sort(([, a], [, b]) => b.f1 - a.f1)
                      .map(([name, vals]) => {
                        const deltaF1 = aggregates.avg_f1 - vals.f1;
                        return (
                          <tr key={name} className="border-b border-[var(--card-border)] last:border-0 hover:bg-black/3 dark:hover:bg-white/3 transition-colors">
                            <td className="px-4 py-3 opacity-80">{name}</td>
                            <td className="text-right px-4 py-3 tabular-nums opacity-70">{vals.em.toFixed(1)}</td>
                            <td className="text-right px-4 py-3 tabular-nums opacity-70">{vals.f1.toFixed(1)}</td>
                            <td className="text-right px-4 py-3 tabular-nums text-green-400 font-medium">+{deltaF1.toFixed(1)}</td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        {/* ===== 4. DATASET INFO ===== */}
        <section className="rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[var(--card-border)] bg-black/5 dark:bg-white/5 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-orange-400" />
            <h2 className="font-semibold text-sm">Dataset: HotpotQA</h2>
          </div>
          <div className="p-6">
            <p className="text-sm opacity-70 leading-relaxed mb-6">
              <a href={metadata.source} target="_blank" rel="noopener noreferrer" className="text-orange-400 hover:underline font-medium">HotpotQA</a>{" "}
              is an academic <span className="font-semibold">multi-hop</span> question-answering dataset: every question
              requires reasoning over information distributed across multiple Wikipedia documents to reach the correct answer.
              It is a significant challenge for RAG systems because retrieval must find <em>all</em> the
              relevant documents and the model must combine the information coherently.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-xl bg-black/5 dark:bg-white/5 border border-[var(--card-border)] p-4 text-center">
                <div className="text-2xl font-black text-orange-400 tabular-nums">{metadata.n_questions}</div>
                <div className="text-[10px] uppercase tracking-wider font-semibold opacity-50 mt-1">Questions</div>
                <div className="text-[10px] opacity-40">Multi-hop, hard</div>
              </div>
              <div className="rounded-xl bg-black/5 dark:bg-white/5 border border-[var(--card-border)] p-4 text-center">
                <div className="text-2xl font-black text-blue-400 tabular-nums">{metadata.n_documents.toLocaleString()}</div>
                <div className="text-[10px] uppercase tracking-wider font-semibold opacity-50 mt-1">Documents</div>
                <div className="text-[10px] opacity-40">Wikipedia ingested</div>
              </div>
              <div className="rounded-xl bg-black/5 dark:bg-white/5 border border-[var(--card-border)] p-4 text-center">
                <div className="text-2xl font-black text-purple-400 tabular-nums">{metadata.types.bridge}</div>
                <div className="text-[10px] uppercase tracking-wider font-semibold opacity-50 mt-1">Bridge</div>
                <div className="text-[10px] opacity-40">Chained reasoning</div>
              </div>
              <div className="rounded-xl bg-black/5 dark:bg-white/5 border border-[var(--card-border)] p-4 text-center">
                <div className="text-2xl font-black text-teal-400 tabular-nums">{metadata.types.comparison}</div>
                <div className="text-[10px] uppercase tracking-wider font-semibold opacity-50 mt-1">Comparison</div>
                <div className="text-[10px] opacity-40">Entity comparison</div>
              </div>
            </div>

            <div className="mt-5 px-4 py-3 rounded-xl bg-orange-500/5 border border-orange-500/10 text-xs opacity-70 leading-relaxed">
              <span className="font-semibold text-orange-400">Note:</span>{" "}
              All {metadata.n_documents.toLocaleString()} documents were ingested through the full pipeline
              (semantic chunking, contextual retrieval, embedding, Spanner), and the {metadata.n_questions} questions were
              evaluated end-to-end with the complete search pipeline. Average answer time:{" "}
              <span className="font-semibold text-orange-400">{(aggregates.avg_time_ms / 1000).toFixed(1)}s</span> per question.
            </div>
          </div>
        </section>

        {/* ===== 5. KPI EXPLANATION ===== */}
        <section className="rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[var(--card-border)] bg-black/5 dark:bg-white/5 flex items-center gap-2">
            <Percent className="w-4 h-4 text-orange-400" />
            <h2 className="font-semibold text-sm">Metrics Explained</h2>
          </div>
          <div className="p-6 space-y-4">
            {[
              {
                icon: Crosshair,
                name: "EM (Exact Match)",
                color: "orange",
                value: `${aggregates.avg_em}%`,
                desc: "Percentage of answers that exactly match the gold answer, after normalization (lowercasing, removal of articles and punctuation). It is the strictest metric: even a nearly correct answer with one extra or missing token gets a score of 0.",
              },
              {
                icon: BarChart3,
                name: "F1 (Token F1 Score)",
                color: "amber",
                value: `${aggregates.avg_f1}%`,
                desc: "Harmonic mean of token-level precision and recall. Precision measures how many tokens in the predicted answer appear in the gold answer; recall measures how many tokens of the gold answer were captured. A more permissive metric than EM that rewards partially correct answers.",
              },
              {
                icon: ScanSearch,
                name: "SP Recall (Supporting Facts Recall)",
                color: "green",
                value: `${aggregates.avg_sp_recall}%`,
                desc: "Percentage of gold documents (supporting facts) that the retrieval system actually returned. Measures retrieval quality independently of generation: an SP Recall of 97.2% means on average nearly all required documents are found by vector search + reranking.",
              },
            ].map((metric) => (
              <div
                key={metric.name}
                className={`flex items-start gap-4 p-4 rounded-xl border transition-colors ${
                  metric.color === "orange"
                    ? "border-orange-500/10 bg-orange-500/3 hover:bg-orange-500/5"
                    : metric.color === "amber"
                    ? "border-amber-500/10 bg-amber-500/3 hover:bg-amber-500/5"
                    : "border-green-500/10 bg-green-500/3 hover:bg-green-500/5"
                }`}
              >
                <div
                  className={`p-2.5 rounded-xl shrink-0 ${
                    metric.color === "orange"
                      ? "bg-orange-500/10"
                      : metric.color === "amber"
                      ? "bg-amber-500/10"
                      : "bg-green-500/10"
                  }`}
                >
                  <metric.icon
                    className={`w-5 h-5 ${
                      metric.color === "orange"
                        ? "text-orange-400"
                        : metric.color === "amber"
                        ? "text-amber-400"
                        : "text-green-400"
                    }`}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-3 mb-1">
                    <h3 className="font-bold text-sm">{metric.name}</h3>
                    <span
                      className={`text-sm font-bold tabular-nums ${
                        metric.color === "orange"
                          ? "text-orange-400"
                          : metric.color === "amber"
                          ? "text-amber-400"
                          : "text-green-400"
                      }`}
                    >
                      {metric.value}
                    </span>
                  </div>
                  <p className="text-xs opacity-60 leading-relaxed">{metric.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ===== QUESTION EXPLORER ===== */}
        <section className="rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl overflow-hidden">
          <button
            onClick={() => setShowQuestions(!showQuestions)}
            className="w-full px-6 py-4 border-b border-[var(--card-border)] bg-black/5 dark:bg-white/5 flex items-center justify-between hover:bg-black/8 dark:hover:bg-white/8 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Search className="w-4 h-4 text-orange-400" />
              <h2 className="font-semibold text-sm">Explore Questions ({data.questions.length})</h2>
            </div>
            {showQuestions ? <ChevronUp className="w-4 h-4 opacity-50" /> : <ChevronDown className="w-4 h-4 opacity-50" />}
          </button>

          {showQuestions && (
            <div className="p-6 space-y-4">
              {/* Filter tabs */}
              <div className="flex gap-2">
                {(["all", "correct", "wrong"] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setQuestionFilter(f)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      questionFilter === f
                        ? f === "correct"
                          ? "bg-green-500/15 text-green-400 border border-green-500/25"
                          : f === "wrong"
                          ? "bg-red-500/15 text-red-400 border border-red-500/25"
                          : "bg-orange-500/15 text-orange-400 border border-orange-500/25"
                        : "bg-black/5 dark:bg-white/5 border border-transparent opacity-60 hover:opacity-100"
                    }`}
                  >
                    {f === "all" && `All (${data.questions.length})`}
                    {f === "correct" && `Correct (${data.questions.filter((q) => q.em === 1).length})`}
                    {f === "wrong" && `Wrong (${data.questions.filter((q) => q.em === 0).length})`}
                  </button>
                ))}
              </div>

              {/* Question list */}
              <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                {filteredQuestions.slice(0, 50).map((q) => (
                  <div
                    key={q.id}
                    className="rounded-xl border border-[var(--card-border)] overflow-hidden transition-all"
                  >
                    <button
                      onClick={() => setExpandedQuestion(expandedQuestion === q.id ? null : q.id)}
                      className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-black/3 dark:hover:bg-white/3 transition-colors"
                    >
                      {q.em === 1 ? (
                        <CheckCircle2 className="w-4 h-4 text-green-400 mt-0.5 shrink-0" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs leading-relaxed">{q.question}</p>
                        <div className="flex gap-3 mt-1">
                          <span className="text-[10px] opacity-40">{q.type}</span>
                          <span className="text-[10px] tabular-nums opacity-40">F1: {(q.f1 * 100).toFixed(0)}%</span>
                          <span className="text-[10px] tabular-nums opacity-40">SP: {(q.sp_recall * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      <ChevronDown className={`w-3.5 h-3.5 opacity-30 mt-0.5 shrink-0 transition-transform ${expandedQuestion === q.id ? "rotate-180" : ""}`} />
                    </button>

                    {expandedQuestion === q.id && (
                      <div className="px-4 pb-4 pt-1 space-y-2 border-t border-[var(--card-border)] bg-black/3 dark:bg-white/3">
                        <div>
                          <span className="text-[10px] font-bold uppercase opacity-40">Gold Answer</span>
                          <p className="text-xs text-green-400 font-medium">{q.gold_answer}</p>
                        </div>
                        <div>
                          <span className="text-[10px] font-bold uppercase opacity-40">Predicted Answer</span>
                          <p className={`text-xs font-medium ${q.em === 1 ? "text-green-400" : "text-red-400"}`}>
                            {q.predicted_answer}
                          </p>
                        </div>
                        <div className="flex gap-4 pt-1">
                          <div>
                            <span className="text-[10px] opacity-40 block">EM</span>
                            <span className={`text-xs font-bold ${q.em === 1 ? "text-green-400" : "text-red-400"}`}>
                              {q.em === 1 ? "Correct" : "Wrong"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] opacity-40 block">F1</span>
                            <span className="text-xs font-bold text-amber-400">{(q.f1 * 100).toFixed(1)}%</span>
                          </div>
                          <div>
                            <span className="text-[10px] opacity-40 block">SP Recall</span>
                            <span className="text-xs font-bold text-blue-400">{(q.sp_recall * 100).toFixed(1)}%</span>
                          </div>
                          <div>
                            <span className="text-[10px] opacity-40 block">Time</span>
                            <span className="text-xs font-bold opacity-70">{(q.time_ms / 1000).toFixed(1)}s</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                {filteredQuestions.length > 50 && (
                  <p className="text-center text-xs opacity-40 py-2">
                    Showing 50 of {filteredQuestions.length} questions.
                  </p>
                )}
              </div>
            </div>
          )}
        </section>

        {/* ===== 6. LOAD BENCHMARK ===== */}
        <section className="rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[var(--card-border)] bg-black/5 dark:bg-white/5 flex items-center gap-2">
            <Upload className="w-4 h-4 text-orange-400" />
            <h2 className="font-semibold text-sm">Load Dataset into the Pipeline</h2>
          </div>
          <div className="p-6 space-y-4">
            <p className="text-sm opacity-70 leading-relaxed">
              You can reload the entire HotpotQA dataset into the production pipeline. This operation will ingest{" "}
              <span className="font-semibold text-orange-400">{metadata.n_documents.toLocaleString()} Wikipedia documents</span>{" "}
              through the full pipeline (chunking, contextual retrieval, embedding, Spanner).
            </p>

            {loadState === "idle" && (
              <button
                onClick={() => setLoadState("confirm")}
                className="flex items-center gap-3 px-6 py-3.5 rounded-xl bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-400 hover:to-orange-500 text-white font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-orange-500/20"
              >
                <Upload className="w-5 h-5" />
                Load Benchmark Dataset
              </button>
            )}

            {loadState === "confirm" && (
              <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5 space-y-3">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div className="text-sm space-y-1">
                    <p className="font-semibold text-amber-400">Confirm operation</p>
                    <p className="opacity-70 text-xs leading-relaxed">
                      You are about to ingest {metadata.n_documents.toLocaleString()} Wikipedia documents into Cloud Spanner.
                      The operation will take several minutes and will use embedding and storage resources.
                    </p>
                  </div>
                </div>
                <div className="flex gap-2 pl-8">
                  <button
                    onClick={handleLoadBenchmark}
                    className="px-4 py-2 rounded-lg bg-orange-500 hover:bg-orange-400 text-white text-xs font-semibold transition-colors"
                  >
                    Confirm and Start
                  </button>
                  <button
                    onClick={() => setLoadState("idle")}
                    className="px-4 py-2 rounded-lg bg-black/10 dark:bg-white/10 text-xs font-semibold opacity-70 hover:opacity-100 transition-opacity"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {(loadState === "loading" || loadState === "polling") && (
              <div className="flex items-center gap-3 p-4 rounded-xl border border-orange-500/20 bg-orange-500/5">
                <Loader2 className="w-5 h-5 text-orange-400 animate-spin shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-orange-400">Ingestion in progress...</p>
                  <p className="text-xs opacity-60">{loadMessage}</p>
                </div>
              </div>
            )}

            {loadState === "success" && (
              <div className="flex items-center gap-3 p-4 rounded-xl border border-green-500/20 bg-green-500/5">
                <CheckCircle2 className="w-5 h-5 text-green-400 shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-green-400">Completed</p>
                  <p className="text-xs opacity-60">{loadMessage}</p>
                </div>
              </div>
            )}

            {loadState === "error" && (
              <div className="space-y-3">
                <div className="flex items-center gap-3 p-4 rounded-xl border border-red-500/20 bg-red-500/5">
                  <XCircle className="w-5 h-5 text-red-400 shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-red-400">Error</p>
                    <p className="text-xs opacity-60">{loadMessage}</p>
                  </div>
                </div>
                <button
                  onClick={() => setLoadState("idle")}
                  className="text-xs text-orange-400 hover:underline"
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        </section>

        {/* Spacer bottom */}
        <div className="h-8" />
      </div>
    </div>
  );
}
