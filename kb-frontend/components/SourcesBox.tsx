"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, FileText, Network, ArrowRight, ImageIcon, DollarSign } from "lucide-react";

interface SourceDoc {
  title: string;
  page: string;
}

interface ImageRef {
  image_id: string;
  doc_id: string;
  chunk_id: string;
  source_doc: string;
  page_number?: number;
}

interface QueryCost {
  total_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  embed_tokens: number;
  spanner_reads: number;
  breakdown?: Record<string, { calls: number; cost_usd: number }>;
}

interface RetrievalMetrics {
  strategy?: string;
  selected_scope?: string;
  chunks_found?: number;
  keyword_candidates?: number;
  vector_candidates?: number;
  graph_boosted?: number;
  image_chunks_found?: number;
  query_cost?: QueryCost;
}

export interface SourcesData {
  documents: SourceDoc[];
  graph: string[];
  chains?: string[];
  images?: ImageRef[];
  retrieval?: RetrievalMetrics;
}

export function parseSourcesFromContent(content: string): {
  cleanContent: string;
  sources: SourcesData | null;
} {
  // If <sources> tag started but hasn't closed yet (still streaming), hide partial block
  if (content.includes("<sources>") && !content.includes("</sources>")) {
    return {
      cleanContent: content.split("<sources>")[0].trim(),
      sources: null,
    };
  }

  const match = content.match(/<sources>([\s\S]*?)<\/sources>/);
  if (!match) return { cleanContent: content, sources: null };

  const cleanContent = content.replace(/<sources>[\s\S]*?<\/sources>/, "").trim();
  try {
    const sources: SourcesData = JSON.parse(match[1].trim());
    return { cleanContent, sources };
  } catch {
    return { cleanContent, sources: null };
  }
}

// Parse "EntityName (Type) -[Rel]-> TargetName (Type)" into structured parts
function parseConnection(conn: string) {
  const match = conn.match(
    /^(.+?)\s*\(([^)]+)\)\s*-\[([^\]]+)\]->\s*(.+?)\s*\(([^)]+)\)$/
  );
  if (match) {
    return {
      srcName: match[1].trim(),
      srcType: match[2].trim(),
      relation: match[3].trim(),
      tgtName: match[4].trim(),
      tgtType: match[5].trim(),
    };
  }
  return null;
}

function GraphConnection({ conn }: { conn: string }) {
  const parsed = parseConnection(conn);
  if (!parsed) {
    // Fallback: render raw text
    return (
      <div className="text-[11px] p-2 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300">
        {conn}
      </div>
    );
  }

  // When name equals type (resolution failed), show only the type name
  const srcHasName = parsed.srcName !== parsed.srcType;
  const tgtHasName = parsed.tgtName !== parsed.tgtType;

  return (
    <div className="flex items-center gap-1.5 text-[11px] p-2 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex-wrap">
      <span className="font-semibold text-slate-700 dark:text-slate-200">
        {parsed.srcName}
      </span>
      {srcHasName && (
        <span className="text-slate-400 dark:text-slate-500 text-[10px]">
          {parsed.srcType}
        </span>
      )}
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 text-[10px] font-medium">
        <ArrowRight className="w-2.5 h-2.5" />
        {parsed.relation}
      </span>
      <span className="font-semibold text-slate-700 dark:text-slate-200">
        {parsed.tgtName}
      </span>
      {tgtHasName && (
        <span className="text-slate-400 dark:text-slate-500 text-[10px]">
          {parsed.tgtType}
        </span>
      )}
    </div>
  );
}

export function SourcesBox({ sources }: { sources: SourcesData }) {
  const [isOpen, setIsOpen] = useState(false);

  const docCount = sources.documents?.length ?? 0;
  const imgCount = sources.images?.length ?? 0;
  // Deduplicate graph connections on the frontend as safety net
  const uniqueGraph = [...new Set(sources.graph ?? [])];
  const uniqueChains = [...new Set(sources.chains ?? [])];
  const graphCount = uniqueGraph.length + uniqueChains.length;

  if (docCount === 0 && graphCount === 0 && imgCount === 0 && !sources.retrieval) return null;

  return (
    <div className="mt-6 mb-1 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden transition-colors duration-200 bg-white dark:bg-slate-900">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors cursor-pointer"
      >
        {isOpen ? (
          <ChevronDown className="w-3.5 h-3.5 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 shrink-0" />
        )}
        <span className="text-slate-700 dark:text-slate-300">Sources &amp; Graph</span>
        <span className="text-slate-400 dark:text-slate-500">
          ({docCount} {docCount === 1 ? "document" : "documents"}, {graphCount}{" "}
          {graphCount === 1 ? "connection" : "connections"}
          {imgCount > 0 && `, ${imgCount} img`}
          {sources.retrieval?.chunks_found && ` · ${sources.retrieval.chunks_found} chunks`}
          {sources.retrieval?.query_cost && ` · $${sources.retrieval.query_cost.total_cost_usd.toFixed(4)}`})
        </span>
      </button>

      {isOpen && (
        <div className="px-4 pb-4 space-y-3 border-t border-slate-200 dark:border-slate-700">
          {/* Documents */}
          {docCount > 0 && (
            <div className="pt-3">
              <h4 className="text-[10px] uppercase tracking-widest font-bold text-slate-400 dark:text-slate-500 mb-2 flex items-center gap-1.5">
                <FileText className="w-3 h-3" /> Source documents
              </h4>
              <div className="space-y-1.5">
                {sources.documents.map((doc, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 text-xs p-2 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  >
                    <FileText className="w-3.5 h-3.5 text-orange-500 shrink-0" />
                    <span className="font-medium truncate text-slate-700 dark:text-slate-200">{doc.title}</span>
                    {doc.page && doc.page !== "N/A" && doc.page !== "null" && (
                      <span className="text-slate-400 dark:text-slate-500 shrink-0">
                        — p. {doc.page}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Graph connections (1-hop) */}
          {uniqueGraph.length > 0 && (
            <div className="pt-2">
              <h4 className="text-[10px] uppercase tracking-widest font-bold text-slate-400 dark:text-slate-500 mb-2 flex items-center gap-1.5">
                <Network className="w-3 h-3" /> Knowledge Graph
              </h4>
              <div className="space-y-1.5">
                {uniqueGraph.map((conn, i) => (
                  <GraphConnection key={i} conn={conn} />
                ))}
              </div>
            </div>
          )}

          {/* Graph chains (2-hop dependency paths) */}
          {uniqueChains.length > 0 && (
            <div className="pt-2">
              <h4 className="text-[10px] uppercase tracking-widest font-bold text-slate-400 dark:text-slate-500 mb-2 flex items-center gap-1.5">
                <Network className="w-3 h-3" /> Dependency Chains
              </h4>
              <div className="space-y-1.5">
                {uniqueChains.map((chain, i) => (
                  <div
                    key={i}
                    className="text-[11px] p-2 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 font-mono"
                  >
                    {chain}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Retrieved images */}
          {imgCount > 0 && (
            <div className="pt-2">
              <h4 className="text-[10px] uppercase tracking-widest font-bold text-slate-400 dark:text-slate-500 mb-2 flex items-center gap-1.5">
                <ImageIcon className="w-3 h-3" /> Retrieved images
              </h4>
              <div className="grid grid-cols-1 gap-2">
                {sources.images!.map((img, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800"
                  >
                    <img
                      src={`/api/image/${img.doc_id}/${img.chunk_id}`}
                      alt={`${img.source_doc} - Page ${img.page_number ?? "?"}`}
                      className="w-full h-auto"
                      loading="lazy"
                    />
                    <div className="p-2 flex items-center justify-between text-[10px]">
                      <span className="text-slate-600 dark:text-slate-300 font-medium truncate">
                        {img.source_doc}
                      </span>
                      {img.page_number && (
                        <span className="text-slate-400 dark:text-slate-500 shrink-0">
                          p. {img.page_number}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Retrieval Metrics */}
          {sources.retrieval && (
            <div className="pt-3">
              <h4 className="text-[10px] uppercase tracking-widest font-bold text-slate-400 dark:text-slate-500 mb-2 flex items-center gap-1.5">
                <Network className="w-3 h-3" /> Retrieval Pipeline
              </h4>
              <div className="grid grid-cols-3 gap-2">
                {sources.retrieval.keyword_candidates != null && (
                  <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2 text-center">
                    <div className="text-sm font-bold text-amber-500">{sources.retrieval.keyword_candidates}</div>
                    <div className="text-[9px] text-slate-400 uppercase">Keyword</div>
                  </div>
                )}
                {sources.retrieval.vector_candidates != null && (
                  <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2 text-center">
                    <div className="text-sm font-bold text-blue-500">{sources.retrieval.vector_candidates}</div>
                    <div className="text-[9px] text-slate-400 uppercase">Vector</div>
                  </div>
                )}
                {sources.retrieval.graph_boosted != null && (
                  <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2 text-center">
                    <div className="text-sm font-bold text-pink-500">{sources.retrieval.graph_boosted}</div>
                    <div className="text-[9px] text-slate-400 uppercase">Graph</div>
                  </div>
                )}
              </div>
              {sources.retrieval.chunks_found != null && (
                <div className="mt-2 text-[10px] text-slate-400 flex items-center gap-2">
                  <span>{sources.retrieval.chunks_found} chunks fused</span>
                  <span>·</span>
                  <span className="capitalize">{sources.retrieval.strategy?.replace("_", " ")}</span>
                  {sources.retrieval.selected_scope && (
                    <>
                      <span>·</span>
                      <span>Scope: <span className="font-semibold capitalize">{sources.retrieval.selected_scope}</span></span>
                    </>
                  )}
                </div>
              )}

              {/* Query Cost */}
              {sources.retrieval.query_cost && (
                <div className="mt-3 flex items-center gap-3 px-3 py-2 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
                  <DollarSign className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  <div className="flex items-center gap-2 text-[10px] flex-wrap">
                    <span className="font-bold text-emerald-600 dark:text-emerald-400">
                      ${sources.retrieval.query_cost.total_cost_usd.toFixed(4)}
                    </span>
                    <span className="text-slate-400">·</span>
                    <span className="text-slate-500 dark:text-slate-400 tabular-nums">
                      {((sources.retrieval.query_cost.input_tokens + sources.retrieval.query_cost.output_tokens) / 1000).toFixed(1)}K tokens
                    </span>
                    {sources.retrieval.query_cost.embed_tokens > 0 && (
                      <>
                        <span className="text-slate-400">·</span>
                        <span className="text-slate-500 dark:text-slate-400 tabular-nums">
                          {(sources.retrieval.query_cost.embed_tokens / 1000).toFixed(1)}K embed
                        </span>
                      </>
                    )}
                    <span className="text-slate-400">·</span>
                    <span className="text-slate-500 dark:text-slate-400 tabular-nums">
                      {sources.retrieval.query_cost.spanner_reads} reads
                    </span>
                    {sources.retrieval.query_cost.breakdown && (
                      <>
                        {Object.entries(sources.retrieval.query_cost.breakdown).map(([api, data]) => (
                          <span key={api} className="text-slate-400 text-[9px]">
                            {api}: ${data.cost_usd.toFixed(4)}
                          </span>
                        ))}
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
