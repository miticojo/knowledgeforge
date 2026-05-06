import React from "react";
import { Database, Network, Cpu, Sparkles, Server, MessageSquare, GitBranch } from "lucide-react";
import { GlossaryTooltip } from "@/components/GlossaryTooltip";

export default function ArchitecturePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 font-sans antialiased py-12 px-4 md:px-8 relative overflow-hidden">
      {/* Grid background pattern */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-20 pointer-events-none" />

      <div className="max-w-7xl mx-auto relative z-10 flex flex-col gap-12">
        {/* Title Header */}
        <div className="text-center space-y-3">
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight bg-gradient-to-b from-white to-slate-400 bg-clip-text text-transparent">
            KnowledgeForge Platform
          </h1>
          <p className="text-sm font-mono text-slate-500 uppercase tracking-widest">
            Blueprint / Reference Flow: Processing vs Query Orchestration
          </p>
        </div>

        {/* Core Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_400px_1fr] gap-8 items-stretch">
          
          {/* LEFT COLUMN: Processing */}
          <div className="bg-slate-900/60 border border-slate-800 backdrop-blur-xl rounded-2xl p-6 border-t-4 border-t-cyan-500 flex flex-col gap-5 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-4">
              <h2 className="text-lg font-bold text-slate-200 flex items-center gap-2">
                <Cpu className="w-5 h-5 text-cyan-400" /> Processing Phase
              </h2>
              <span className="text-[10px] font-mono bg-slate-950 border border-slate-800 px-2.5 py-1 rounded-full text-cyan-400">
                Vertex Agent Engine
              </span>
            </div>

            {/* Steps */}
            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-cyan-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" /> 1. Sources / Ingestion
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Automated collection from remote object storage and shared document repositories.
              </p>
              <div className="flex gap-1.5 pt-1">
                <span className="text-[9px] font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">GCS</span>
                <span className="text-[9px] font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">Sharepoint</span>
              </div>
            </div>

            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-cyan-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" /> 2. Processing Agent (<GlossaryTooltip term="ADK">ADK</GlossaryTooltip>)
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Specialized agent responsible for normalizing multi-format documents (PDF/DOCX/XLSX). Tools are exposed via <GlossaryTooltip term="MCP">MCP</GlossaryTooltip>.
              </p>
            </div>

            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-cyan-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" /> 3. Multi-Modal Extraction
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Delegates to Gemini 3.1 Flash to extract relational entities, nouns, and structured metadata. Schema follows <GlossaryTooltip term="ArchiMate">ArchiMate</GlossaryTooltip>; entity reconciliation uses <GlossaryTooltip term="iText2KG">iText2KG</GlossaryTooltip>.
              </p>
              <div className="flex gap-1.5 pt-1">
                <span className="text-[9px] font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">Graph Nouns</span>
                <span className="text-[9px] font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">Rel Types</span>
              </div>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <GlossaryTooltip term="EXTRACTED">
                  <span className="text-[9px] font-mono bg-emerald-950/60 border border-emerald-700/50 text-emerald-300 px-2 py-0.5 rounded">EXTRACTED</span>
                </GlossaryTooltip>
                <GlossaryTooltip term="INFERRED">
                  <span className="text-[9px] font-mono bg-amber-950/60 border border-amber-700/50 text-amber-300 px-2 py-0.5 rounded">INFERRED</span>
                </GlossaryTooltip>
                <GlossaryTooltip term="AMBIGUOUS">
                  <span className="text-[9px] font-mono bg-rose-950/60 border border-rose-700/50 text-rose-300 px-2 py-0.5 rounded">AMBIGUOUS</span>
                </GlossaryTooltip>
              </div>
            </div>

            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-cyan-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" /> 4. Vectorization
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Synthesizes semantic density into Float64 array spaces using Gemini Embeddings 2.0.
              </p>
            </div>
          </div>

          {/* CENTER COLUMN: Spanner Pillar */}
          <div className="relative flex flex-col items-center justify-center bg-gradient-to-b from-slate-900 to-slate-950 border-2 border-orange-500/40 rounded-3xl p-8 shadow-[0_0_50px_rgba(249,115,22,0.15)] overflow-hidden group">
            {/* Inner glow */}
            <div className="absolute w-80 h-80 bg-orange-500/10 rounded-full blur-3xl pointer-events-none group-hover:bg-orange-500/20 transition-colors duration-700" />
            
            <div className="relative z-10 flex flex-col items-center text-center gap-6 w-full">
              <div className="p-4 bg-orange-500/10 border border-orange-500/30 rounded-2xl text-orange-400">
                <Database className="w-8 h-8 animate-pulse" />
              </div>

              <div className="space-y-1">
                <h3 className="text-2xl font-extrabold text-orange-400 font-mono tracking-tight">
                  Google Cloud Spanner
                </h3>
                <p className="text-xs text-slate-400">
                  Hybrid Store: Relation Graph (GQL) + Double-Precision Vector Base.
                </p>
              </div>

              {/* Schema Display */}
              <div className="w-full bg-black/40 border border-dashed border-orange-500/30 rounded-xl p-4 text-left space-y-2 backdrop-blur-sm">
                <div className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-widest border-b border-slate-800 pb-1">
                  TABLE.DOCUMENTS
                </div>
                <div className="flex justify-between text-xs font-mono text-slate-300">
                  <span>id</span> <span className="text-orange-400/80">STRING</span>
                </div>
                <div className="flex justify-between text-xs font-mono text-slate-300">
                  <span>content_chunk</span> <span className="text-orange-400/80">TEXT</span>
                </div>
                <div className="flex justify-between text-xs font-mono text-slate-300">
                  <span>vector_embedding</span> <span className="text-orange-400/80">ARRAY&lt;FLOAT64&gt;</span>
                </div>
              </div>

              <div className="w-full bg-black/40 border border-dashed border-orange-500/30 rounded-xl p-4 text-left space-y-2 backdrop-blur-sm">
                <div className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-widest border-b border-slate-800 pb-1">
                  TABLE.RELATIONS
                </div>
                <div className="flex justify-between text-xs font-mono text-slate-300">
                  <span>src_node</span> <span className="text-orange-400/80">STRING</span>
                </div>
                <div className="flex justify-between text-xs font-mono text-slate-300">
                  <span>rel_type</span> <span className="text-orange-400/80">ENUM</span>
                </div>
                <div className="flex justify-between text-xs font-mono text-slate-300">
                  <span>tgt_node</span> <span className="text-orange-400/80">STRING</span>
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN: Query Orchestration */}
          <div className="bg-slate-900/60 border border-slate-800 backdrop-blur-xl rounded-2xl p-6 border-t-4 border-t-green-500 flex flex-col gap-5 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-4">
              <h2 className="text-lg font-bold text-slate-200 flex items-center gap-2">
                <GitBranch className="w-5 h-5 text-green-400" /> Query Phase
              </h2>
              <span className="text-[10px] font-mono bg-slate-950 border border-slate-800 px-2.5 py-1 rounded-full text-green-400">
                Agent Engine
              </span>
            </div>

            {/* Steps */}
            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-green-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" /> 1. Action Trigger
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                User inputs natural language questions; the browser streams over <GlossaryTooltip term="AG-UI">AG-UI</GlossaryTooltip> SSE.
              </p>
            </div>

            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-green-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" /> 2. <GlossaryTooltip term="Coordinator">Coordinator</GlossaryTooltip> Agent
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Maintains execution planning, dedupes invocations, and proxies tasks to Sub-Agents.
              </p>
            </div>

            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-green-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" /> 3. Search Agent
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Executes a <GlossaryTooltip term="GraphRAG">GraphRAG</GlossaryTooltip> + <GlossaryTooltip term="AgenticRAG">AgenticRAG</GlossaryTooltip> hybrid: Spanner graph navigation (inspired by <GlossaryTooltip term="HippoRAG">HippoRAG</GlossaryTooltip>) paired with BM25 scoring fused via <GlossaryTooltip term="RRF">RRF</GlossaryTooltip>.
              </p>
              <div className="flex gap-1.5 pt-1">
                <span className="text-[9px] font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">GQL</span>
                <span className="text-[9px] font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">RAG</span>
              </div>
            </div>

            <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-mono font-semibold text-green-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" /> 4. Enterprise Integration
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Connects out to external Data Warehouses (BigQuery / Dataplex) for specific statistics.
              </p>
            </div>
          </div>

        </div>
      </div>
    </main>
  );
}
