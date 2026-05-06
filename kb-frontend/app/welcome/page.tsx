import React from "react";
import Link from "next/link";
import {
  Sparkles,
  ArrowRight,
  Upload,
  Network,
  Bot,
  Plug,
  BookOpen,
  GitBranch,
  Cpu,
} from "lucide-react";

type Capability = {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
  href: string;
  cta: string;
  accent: string;
};

const CAPABILITIES: Capability[] = [
  {
    icon: Upload,
    title: "Ingest anything",
    body:
      "PDF, DOCX, PPTX documents and Git repos parsed via AST for Python, TypeScript, Java, Go and SQL.",
    href: "/ingestion",
    cta: "Open the ingestion console",
    accent: "cyan",
  },
  {
    icon: Network,
    title: "GraphRAG over ArchiMate 3.2",
    body:
      "22 entity types, 11 relationship types, every edge labelled with extraction confidence for honest retrieval.",
    href: "/architecture",
    cta: "See the schema in action",
    accent: "orange",
  },
  {
    icon: Bot,
    title: "AgenticRAG",
    body:
      "A coordinator fans out to vector, graph, keyword and reranker workers — every claim is verified before it ships.",
    href: "/benchmark",
    cta: "Inspect benchmark traces",
    accent: "green",
  },
  {
    icon: Plug,
    title: "MCP-native",
    body:
      "Distributable as a Gemini CLI / MCP IDE / Codex extension; coexists cleanly with Google's data-agent-kit.",
    href: "/architecture",
    cta: "Read the integration guide",
    accent: "purple",
  },
];

const ACCENT_STYLES: Record<
  string,
  { ring: string; glow: string; icon: string; chip: string; link: string }
> = {
  cyan: {
    ring: "border-t-cyan-500",
    glow: "shadow-[0_0_60px_-30px_rgba(6,182,212,0.7)]",
    icon: "text-cyan-400 bg-cyan-500/10 border-cyan-500/30",
    chip: "text-cyan-400",
    link: "text-cyan-400 hover:text-cyan-300",
  },
  orange: {
    ring: "border-t-orange-500",
    glow: "shadow-[0_0_60px_-30px_rgba(249,115,22,0.7)]",
    icon: "text-orange-400 bg-orange-500/10 border-orange-500/30",
    chip: "text-orange-400",
    link: "text-orange-400 hover:text-orange-300",
  },
  green: {
    ring: "border-t-green-500",
    glow: "shadow-[0_0_60px_-30px_rgba(34,197,94,0.7)]",
    icon: "text-green-400 bg-green-500/10 border-green-500/30",
    chip: "text-green-400",
    link: "text-green-400 hover:text-green-300",
  },
  purple: {
    ring: "border-t-purple-500",
    glow: "shadow-[0_0_60px_-30px_rgba(168,85,247,0.7)]",
    icon: "text-purple-400 bg-purple-500/10 border-purple-500/30",
    chip: "text-purple-400",
    link: "text-purple-400 hover:text-purple-300",
  },
};

export default function WelcomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 font-sans antialiased relative overflow-hidden">
      {/* Grid background pattern — same idiom as /architecture */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_30%,#000_70%,transparent_100%)] opacity-20 pointer-events-none" />

      {/* Ambient orange glow */}
      <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[40rem] h-[40rem] bg-orange-500/10 rounded-full blur-[120px] pointer-events-none" />

      <div className="max-w-7xl mx-auto relative z-10 px-4 md:px-8 py-16 md:py-24 flex flex-col gap-20">
        {/* HERO */}
        <section className="flex flex-col items-center text-center gap-8">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-orange-500/30 bg-orange-500/5 text-[10px] font-mono uppercase tracking-widest text-orange-400">
            <Sparkles className="w-3 h-3" />
            <span>KnowledgeForge · v0 preview</span>
          </div>

          <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight max-w-5xl">
            <span className="bg-gradient-to-b from-white to-slate-400 bg-clip-text text-transparent">
              KnowledgeForge —{" "}
            </span>
            <span className="bg-gradient-to-r from-orange-400 via-orange-300 to-amber-200 bg-clip-text text-transparent">
              AgenticRAG over GraphRAG
            </span>
            <span className="bg-gradient-to-b from-white to-slate-400 bg-clip-text text-transparent">
              {" "}on Google Cloud
            </span>
          </h1>

          <p className="max-w-2xl text-base md:text-lg text-slate-400 leading-relaxed">
            Forge a verifiable knowledge base from your documents and code. A
            coordinator agent orchestrates hybrid retrieval — vector, graph,
            keyword and reranker — over an ArchiMate-typed graph stored in
            Spanner, so every answer cites a real edge.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
            <Link
              href="/chat?prompt=What%20components%20are%20in%20this%20system%3F"
              className="group inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-b from-orange-500 to-orange-600 text-white font-semibold text-sm shadow-lg shadow-orange-900/40 hover:from-orange-400 hover:to-orange-500 active:scale-[0.98] transition-all"
            >
              Try a demo query
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <Link
              href="/ingestion"
              className="group inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-slate-900 border border-slate-700 text-slate-200 font-semibold text-sm hover:border-slate-500 hover:bg-slate-800 active:scale-[0.98] transition-all"
            >
              <Upload className="w-4 h-4" />
              Ingest a repo
            </Link>
          </div>
        </section>

        {/* CAPABILITIES — 2x2 grid */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {CAPABILITIES.map((cap) => {
            const style = ACCENT_STYLES[cap.accent];
            const Icon = cap.icon;
            return (
              <article
                key={cap.title}
                className={`group relative bg-slate-900/60 border border-slate-800 backdrop-blur-xl rounded-2xl p-6 border-t-4 ${style.ring} ${style.glow} flex flex-col gap-4 transition-all hover:border-slate-700 hover:-translate-y-0.5`}
              >
                <div className="flex items-start justify-between">
                  <div
                    className={`p-3 rounded-xl border ${style.icon}`}
                    aria-hidden="true"
                  >
                    <Icon className="w-6 h-6" />
                  </div>
                  <span
                    className={`text-[10px] font-mono uppercase tracking-widest ${style.chip} opacity-70`}
                  >
                    Pillar
                  </span>
                </div>

                <div className="flex flex-col gap-2">
                  <h2 className="text-xl font-bold text-slate-100">
                    {cap.title}
                  </h2>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    {cap.body}
                  </p>
                </div>

                <Link
                  href={cap.href}
                  className={`mt-auto inline-flex items-center gap-1.5 text-xs font-semibold ${style.link} transition-colors`}
                >
                  Learn more
                  <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              </article>
            );
          })}
        </section>

        {/* HOW IT WORKS */}
        <section className="flex flex-col gap-6">
          <div className="text-center space-y-2">
            <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              03 · Continue exploring
            </p>
            <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight bg-gradient-to-b from-white to-slate-400 bg-clip-text text-transparent">
              How it works
            </h2>
            <p className="text-sm text-slate-400 max-w-xl mx-auto">
              Three lenses on the same system — pick the one that matches how
              you learn best.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Link
              href="/architecture"
              className="group bg-slate-900/60 border border-slate-800 rounded-2xl p-5 hover:border-cyan-500/40 transition-all flex flex-col gap-3"
            >
              <Cpu className="w-5 h-5 text-cyan-400" />
              <div className="flex flex-col gap-1">
                <span className="text-sm font-bold text-slate-100">
                  Architecture
                </span>
                <span className="text-xs text-slate-400">
                  Processing vs query orchestration, end to end.
                </span>
              </div>
              <span className="text-[10px] font-mono uppercase tracking-widest text-cyan-400 inline-flex items-center gap-1 mt-auto">
                /architecture <ArrowRight className="w-3 h-3" />
              </span>
            </Link>

            <Link
              href="/benchmark"
              className="group bg-slate-900/60 border border-slate-800 rounded-2xl p-5 hover:border-green-500/40 transition-all flex flex-col gap-3"
            >
              <GitBranch className="w-5 h-5 text-green-400" />
              <div className="flex flex-col gap-1">
                <span className="text-sm font-bold text-slate-100">
                  Benchmark
                </span>
                <span className="text-xs text-slate-400">
                  HotpotQA traces and retrieval quality scoreboards.
                </span>
              </div>
              <span className="text-[10px] font-mono uppercase tracking-widest text-green-400 inline-flex items-center gap-1 mt-auto">
                /benchmark <ArrowRight className="w-3 h-3" />
              </span>
            </Link>

            <a
              href="/docs/concepts/rag-primer.md"
              className="group bg-slate-900/60 border border-slate-800 rounded-2xl p-5 hover:border-orange-500/40 transition-all flex flex-col gap-3"
            >
              <BookOpen className="w-5 h-5 text-orange-400" />
              <div className="flex flex-col gap-1">
                <span className="text-sm font-bold text-slate-100">
                  RAG primer
                </span>
                <span className="text-xs text-slate-400">
                  Why GraphRAG, why agents, and what they cost.
                </span>
              </div>
              <span className="text-[10px] font-mono uppercase tracking-widest text-orange-400 inline-flex items-center gap-1 mt-auto">
                docs/concepts <ArrowRight className="w-3 h-3" />
              </span>
            </a>
          </div>
        </section>
      </div>
    </main>
  );
}
