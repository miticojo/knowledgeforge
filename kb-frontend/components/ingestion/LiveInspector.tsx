"use client";

import {
  ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { ExternalLink, Loader2, X, AlertCircle } from "lucide-react";
import RoutingBadge from "./RoutingBadge";
import { LAYER_COLORS, Layer } from "@/lib/archimate";
import type { EdgeLite, EntityLite } from "@/lib/use-ingest-events";

export interface LiveInspectorArtifact {
  file: string;
  parser: string;
  source: string;
  language: string;
  parsed: unknown;
  entities: EntityLite[];
  edges: EdgeLite[];
}

export interface LiveInspectorProps {
  jobId: string;
  selectedFile: string | null;
  parser: string | null;
  onClose: () => void;
  /** Tenant id for X-Tenant-Id header on artifact fetches. */
  tenantId?: string;
  /** Inject artifact for tests; bypasses fetch. */
  injectedArtifact?: LiveInspectorArtifact | null;
}

const SOURCE_LANGS = new Set([
  "python",
  "typescript",
  "javascript",
  "go",
  "java",
  "sql",
]);

function LineNumberedCode({ source }: { source: string }) {
  const lines = source.split("\n");
  return (
    <div className="flex h-full min-h-0 overflow-auto rounded-lg border border-white/10 bg-[#0a0a0a]">
      <pre
        aria-hidden="true"
        className="select-none border-r border-white/5 bg-black/40 px-2 py-3 text-right font-mono text-[10px] leading-[1.55] text-white/30"
      >
        {lines.map((_, i) => `${i + 1}\n`).join("")}
      </pre>
      <pre className="flex-1 overflow-x-auto px-3 py-3 font-mono text-[11px] leading-[1.55] text-white/85">
        <code>{source}</code>
      </pre>
    </div>
  );
}

// Tiny markdown renderer: headings, paragraphs, lists, fenced code.
function renderMarkdown(src: string): ReactNode {
  const lines = src.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }
      i++;
      out.push(
        <pre
          key={key++}
          className="my-2 overflow-x-auto rounded-md border border-white/10 bg-black/60 p-2 font-mono text-[11px] text-emerald-200"
        >
          <code>{buf.join("\n")}</code>
        </pre>
      );
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const text = h[2];
      const sizeCls =
        level <= 1
          ? "text-base font-bold"
          : level === 2
          ? "text-sm font-bold"
          : "text-xs font-bold";
      out.push(
        <div key={key++} className={`${sizeCls} mt-3 mb-1 text-orange-300`}>
          {text}
        </div>
      );
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      out.push(
        <ul
          key={key++}
          className="my-2 list-disc space-y-0.5 pl-5 text-[12px] text-white/80"
        >
          {items.map((it, idx) => (
            <li key={idx}>{it}</li>
          ))}
        </ul>
      );
      continue;
    }
    if (line.trim() === "") {
      i++;
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("#") &&
      !lines[i].startsWith("```") &&
      !/^\s*[-*]\s+/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push(
      <p key={key++} className="my-1.5 text-[12px] leading-relaxed text-white/80">
        {para.join(" ")}
      </p>
    );
  }
  return <div className="px-1">{out}</div>;
}

function JsonTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  const [open, setOpen] = useState(depth < 2);
  if (value === null) return <span className="text-white/40">null</span>;
  if (typeof value === "string")
    return <span className="text-emerald-300">&quot;{value}&quot;</span>;
  if (typeof value === "number" || typeof value === "boolean")
    return <span className="text-amber-300">{String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-white/40">[]</span>;
    return (
      <span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-white/60 hover:text-white"
        >
          {open ? "▾" : "▸"} [{value.length}]
        </button>
        {open && (
          <ul className="ml-3 border-l border-white/10 pl-2">
            {value.map((v, i) => (
              <li key={i}>
                <span className="text-white/40">{i}: </span>
                <JsonTree value={v} depth={depth + 1} />
              </li>
            ))}
          </ul>
        )}
      </span>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-white/40">{"{}"}</span>;
    return (
      <span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-white/60 hover:text-white"
        >
          {open ? "▾" : "▸"} {`{${entries.length}}`}
        </button>
        {open && (
          <ul className="ml-3 border-l border-white/10 pl-2">
            {entries.map(([k, v]) => (
              <li key={k}>
                <span className="text-blue-300">{k}</span>
                <span className="text-white/40">: </span>
                <JsonTree value={v} depth={depth + 1} />
              </li>
            ))}
          </ul>
        )}
      </span>
    );
  }
  return <span className="text-white/40">{String(value)}</span>;
}

type FnLike = string | { name?: string; qualified_name?: string; signature?: string };
type ClassLike =
  | { name?: string; methods?: FnLike[] }
  | string;

interface ModuleNode {
  module?: string;
  module_name?: string;
  classes?: ClassLike[];
  functions?: FnLike[];
  imports?: Array<string | { module?: string; name?: string }>;
}

function fnLabel(f: FnLike): string {
  if (typeof f === "string") return f;
  if (!f) return "";
  return f.name || f.qualified_name || "";
}

function importLabel(i: string | { module?: string; name?: string }): string {
  if (typeof i === "string") return i;
  if (!i) return "";
  return i.module ? `${i.module}${i.name ? "." + i.name : ""}` : i.name || "";
}

function ModulesTree({ parsed }: { parsed: unknown }) {
  const raw = (parsed as ModuleNode) || {};
  // ParsedFile from backend may nest under .module or .module_name; support both.
  const modName = raw.module || raw.module_name;
  return (
    <ul className="space-y-1 text-[11px]">
      {modName && <li className="font-mono text-orange-300">module: {modName}</li>}
      {raw.imports && raw.imports.length > 0 && (
        <li>
          <div className="text-[10px] font-bold uppercase text-white/40">imports</div>
          <ul className="ml-3 list-disc text-white/70">
            {raw.imports.map((imp, i) => (
              <li key={i} className="font-mono">{importLabel(imp)}</li>
            ))}
          </ul>
        </li>
      )}
      {raw.classes && raw.classes.length > 0 && (
        <li>
          <div className="text-[10px] font-bold uppercase text-white/40">classes</div>
          <ul className="ml-3">
            {raw.classes.map((c, i) => {
              const cls = typeof c === "string" ? { name: c } : c || {};
              return (
                <li key={i}>
                  <span className="font-mono text-blue-300">{cls.name || ""}</span>
                  {cls.methods && cls.methods.length > 0 && (
                    <ul className="ml-4 list-disc text-white/70">
                      {cls.methods.map((mm, j) => (
                        <li key={j} className="font-mono">{fnLabel(mm)}()</li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </li>
      )}
      {raw.functions && raw.functions.length > 0 && (
        <li>
          <div className="text-[10px] font-bold uppercase text-white/40">functions</div>
          <ul className="ml-3 list-disc text-white/70">
            {raw.functions.map((fn, i) => (
              <li key={i} className="font-mono">{fnLabel(fn)}()</li>
            ))}
          </ul>
        </li>
      )}
    </ul>
  );
}

interface LiteparseSection {
  title?: string;
  level?: number;
  page?: number;
}

interface LiteparseDoc {
  sections?: LiteparseSection[];
  image_count?: number;
  page_count?: number;
}

function LiteparseTree({ parsed }: { parsed: unknown }) {
  const doc = (parsed as LiteparseDoc) || {};
  const sections = Array.isArray(doc.sections) ? doc.sections : [];
  return (
    <div className="space-y-3 text-[11px]">
      <div className="flex flex-wrap gap-2">
        {typeof doc.page_count === "number" && (
          <span className="rounded-md border border-white/10 bg-black/30 px-2 py-0.5 font-mono text-[10px] text-white/70">
            pages: <span className="text-emerald-300">{doc.page_count}</span>
          </span>
        )}
        <span className="rounded-md border border-white/10 bg-black/30 px-2 py-0.5 font-mono text-[10px] text-white/70">
          images: <span className="text-emerald-300">{doc.image_count ?? 0}</span>
        </span>
        <span className="rounded-md border border-white/10 bg-black/30 px-2 py-0.5 font-mono text-[10px] text-white/70">
          sections: <span className="text-emerald-300">{sections.length}</span>
        </span>
      </div>

      {sections.length > 0 ? (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-white/40">
            Sections
          </div>
          <ul className="space-y-0.5">
            {sections.map((s, i) => {
              const level = Math.min(Math.max(s.level ?? 1, 1), 6);
              const indent = (level - 1) * 12;
              return (
                <li
                  key={i}
                  className="flex items-baseline gap-2 font-mono text-[11px] text-white/85"
                  style={{ paddingLeft: indent }}
                >
                  <span className="text-orange-300/70">H{level}</span>
                  <span className="truncate">{s.title || "(untitled)"}</span>
                  {typeof s.page === "number" && (
                    <span className="ml-auto text-[10px] text-white/40">
                      p.{s.page}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <div className="text-[11px] text-white/40">No sections detected.</div>
      )}
    </div>
  );
}

interface SqlSchema {
  tables?: Array<{
    name: string;
    columns?: Array<{ name: string; type?: string }>;
    foreign_keys?: Array<{ column: string; references: string }>;
  }>;
}

function SqlTablesTree({ parsed }: { parsed: unknown }) {
  const s = (parsed as SqlSchema) || {};
  if (!s.tables || s.tables.length === 0) {
    return <div className="text-[11px] text-white/40">No tables found.</div>;
  }
  return (
    <ul className="space-y-2 text-[11px]">
      {s.tables.map((t, i) => (
        <li
          key={i}
          className="rounded-md border border-white/10 bg-black/30 p-2"
        >
          <div className="font-mono text-emerald-300">{t.name}</div>
          {t.columns && t.columns.length > 0 && (
            <ul className="ml-3 mt-1 list-disc text-white/70">
              {t.columns.map((c, j) => (
                <li key={j} className="font-mono">
                  {c.name} <span className="text-white/40">{c.type ?? ""}</span>
                </li>
              ))}
            </ul>
          )}
          {t.foreign_keys && t.foreign_keys.length > 0 && (
            <div className="ml-3 mt-1 text-[10px] text-amber-300">
              FK:{" "}
              {t.foreign_keys.map((fk, k) => (
                <span key={k} className="mr-2 font-mono">
                  {fk.column} ──&gt; {fk.references}
                </span>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function EntityChips({ entities }: { entities: EntityLite[] }) {
  if (entities.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entities.map((e) => {
        const color = LAYER_COLORS[e.layer as Layer] ?? "#94a3b8";
        return (
          <span
            key={e.id}
            data-testid="li-entity-chip"
            title={`${e.type} · ${e.layer} · ${e.confidence}`}
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
            {e.name}
          </span>
        );
      })}
    </div>
  );
}

function EdgeChips({ edges }: { edges: EdgeLite[] }) {
  if (edges.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {edges.map((e, i) => (
        <span
          key={`${e.source}-${e.rel}-${e.target}-${i}`}
          data-testid="li-edge-chip"
          className="rounded-md border border-white/10 bg-black/30 px-1.5 py-0.5 font-mono text-[10px] text-white/70"
          title={`${e.source} → ${e.target} (${e.confidence})`}
        >
          <span className="text-blue-300">{shortId(e.source)}</span>
          <span className="text-white/40">{` ──${e.rel}──> `}</span>
          <span className="text-emerald-300">{shortId(e.target)}</span>
        </span>
      ))}
    </div>
  );
}

function shortId(id: string): string {
  if (id.length <= 18) return id;
  return id.slice(0, 8) + "…" + id.slice(-6);
}

// Module-level cache shared across instances; keyed by jobId+file.
const artifactCache = new Map<string, LiveInspectorArtifact>();

export default function LiveInspector({
  jobId,
  selectedFile,
  parser,
  onClose,
  tenantId = "",
  injectedArtifact,
}: LiveInspectorProps) {
  const [artifact, setArtifact] = useState<LiveInspectorArtifact | null>(
    injectedArtifact ?? null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (injectedArtifact) {
      setArtifact(injectedArtifact);
      return;
    }
    if (!selectedFile || !jobId) {
      setArtifact(null);
      return;
    }
    const cacheKey = `${jobId}::${selectedFile}`;
    const cached = artifactCache.get(cacheKey);
    if (cached) {
      setArtifact(cached);
      setError(null);
      return;
    }

    const myReq = ++reqIdRef.current;
    setLoading(true);
    setError(null);
    setArtifact(null);

    const url = `/api/ingest/${encodeURIComponent(jobId)}/file?path=${encodeURIComponent(selectedFile)}`;
    fetch(url, { headers: { "X-Tenant-Id": tenantId } })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as LiveInspectorArtifact;
      })
      .then((data) => {
        if (myReq !== reqIdRef.current) return;
        artifactCache.set(cacheKey, data);
        setArtifact(data);
      })
      .catch((err: unknown) => {
        if (myReq !== reqIdRef.current) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        // Auto-retry on 404 — happens when the inspector mounts/auto-selects
        // before the backend has stored the artifact (parse_end not yet emitted).
        if (msg.includes("404")) {
          setTimeout(() => {
            if (myReq !== reqIdRef.current) return;
            setError(null);
            // bump reqId to force a fresh effect run via the deps proxy below
            setRetryTick((n) => n + 1);
          }, 2500);
        }
      })
      .finally(() => {
        if (myReq !== reqIdRef.current) return;
        setLoading(false);
      });
  }, [jobId, selectedFile, tenantId, injectedArtifact, retryTick]);

  const focusEntityId = useMemo(() => {
    if (!artifact?.entities?.length) return null;
    return artifact.entities[0].id;
  }, [artifact]);

  const language = artifact?.language || "";
  const parserStr = parser || artifact?.parser || "";

  if (!selectedFile) {
    return (
      <div className="flex h-full items-center justify-center text-[11px] text-white/40">
        Select a file from the list above to inspect parsed entities.
      </div>
    );
  }

  return (
    <section
      aria-label="Live inspector"
      className="flex h-full min-h-0 flex-col bg-black/30"
    >
      <header className="flex items-center gap-2 border-b border-white/10 bg-black/40 px-4 py-2">
        <span
          className="truncate font-mono text-[11px] text-white/85"
          title={selectedFile}
        >
          {selectedFile}
        </span>
        {parserStr && <RoutingBadge parser={parserStr} />}
        <div className="ml-auto flex items-center gap-2">
          {focusEntityId && (
            <Link
              href={`/graph?focus=${encodeURIComponent(focusEntityId)}`}
              className="inline-flex items-center gap-1 rounded-md border border-pink-400/30 bg-pink-500/10 px-2 py-0.5 text-[10px] font-semibold text-pink-300 hover:bg-pink-500/20"
            >
              <ExternalLink className="h-3 w-3" /> Open in /graph
            </Link>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close inspector"
            className="rounded-md p-1 text-white/50 hover:bg-white/10 hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {loading && (
        <div className="flex flex-1 items-center justify-center gap-2 text-[11px] text-white/50">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading artifact…
        </div>
      )}

      {error && (
        <div className="m-3 flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-[11px] text-red-200">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>Could not load artifact: {error}</span>
        </div>
      )}

      {artifact && (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
          {/* Source pane */}
          <div className="min-h-0 overflow-hidden border-b border-white/10 p-3 lg:border-b-0 lg:border-r">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-white/50">
              Source · {language || "raw"}
            </div>
            <div className="h-[calc(100%-1.25rem)]">
              {language === "pdf" ? (
                <embed
                  data-testid="li-pdf-embed"
                  src={`/api/ingest/${encodeURIComponent(jobId)}/file/raw?path=${encodeURIComponent(artifact.file)}`}
                  type="application/pdf"
                  className="h-full w-full rounded-lg border border-white/10 bg-[#0a0a0a]"
                />
              ) : language === "markdown" ? (
                <div className="h-full overflow-auto rounded-lg border border-white/10 bg-[#0a0a0a] p-3">
                  {renderMarkdown(artifact.source || "")}
                </div>
              ) : SOURCE_LANGS.has(language) ? (
                <LineNumberedCode source={artifact.source || ""} />
              ) : (
                <pre className="h-full overflow-auto rounded-lg border border-white/10 bg-[#0a0a0a] p-3 font-mono text-[11px] text-white/80">
                  {artifact.source || ""}
                </pre>
              )}
            </div>
          </div>

          {/* Parsed pane */}
          <div className="min-h-0 overflow-y-auto p-3">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-white/50">
              Parsed · {parserStr || "unknown"}
            </div>

            <div className="rounded-lg border border-white/10 bg-black/40 p-3 text-[11px]">
              {parserStr === "liteparse" ? (
                <LiteparseTree parsed={artifact.parsed} />
              ) : parserStr === "gemini-markdown" ? (
                <JsonTree value={artifact.parsed} />
              ) : parserStr === "sqlglot" ? (
                <SqlTablesTree parsed={artifact.parsed} />
              ) : parserStr === "python-ast" ||
                parserStr.startsWith("tree-sitter") ? (
                <ModulesTree parsed={artifact.parsed} />
              ) : (
                <JsonTree value={artifact.parsed} />
              )}
            </div>

            <div className="mt-3">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-white/50">
                Entities ({artifact.entities.length})
              </div>
              <EntityChips entities={artifact.entities} />
            </div>

            <div className="mt-3">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-white/50">
                Edges ({artifact.edges.length})
              </div>
              <EdgeChips edges={artifact.edges} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
