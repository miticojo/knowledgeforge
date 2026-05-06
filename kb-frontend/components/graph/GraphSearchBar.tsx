"use client";

import * as Popover from "@radix-ui/react-popover";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useGraphStore } from "@/lib/graph-store";
import { LAYER_COLORS, type Layer } from "@/lib/archimate";

export interface SearchResult {
  id: string;
  name: string;
  type: string;
  layer: string;
}

interface GraphSearchBarProps {
  /** Override fetch endpoint (used in tests). */
  endpoint?: string;
  /** Debounce window in ms. Default 250. */
  debounceMs?: number;
}

const TYPE_GLYPH: Record<string, string> = {
  Capability: "◆",
  BusinessActor: "●",
  BusinessRole: "◐",
  BusinessProcess: "▶",
  BusinessFunction: "■",
  BusinessService: "◉",
  BusinessObject: "▣",
  Contract: "§",
  ApplicationComponent: "▤",
  ApplicationService: "◈",
  ApplicationInterface: "⌬",
  DataObject: "▦",
  Node: "▼",
  Device: "▽",
  SystemSoftware: "◇",
  TechnologyService: "◊",
  CommunicationNetwork: "≈",
  Artifact: "▲",
  Stakeholder: "☉",
  Goal: "★",
  Requirement: "✦",
  Constraint: "✕",
};

function layerColor(layer: string): string {
  return (LAYER_COLORS as Record<string, string>)[layer] ?? "#94a3b8";
}

export function GraphSearchBar({
  endpoint = "/api/graph/search",
  debounceMs = 250,
}: GraphSearchBarProps) {
  const toggleSelect = useGraphStore((s) => s.toggleSelect);

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Cmd/Ctrl + K -> focus and open.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Debounced fetch.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    const t = window.setTimeout(() => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      fetch(`${endpoint}?q=${encodeURIComponent(q)}&limit=20`, {
        signal: ac.signal,
      })
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((data) => {
          const list: SearchResult[] = Array.isArray(data)
            ? data
            : Array.isArray(data?.results)
            ? data.results
            : [];
          setResults(list);
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          setError(err instanceof Error ? err.message : "Search failed");
          setLoading(false);
        });
    }, debounceMs);
    return () => window.clearTimeout(t);
  }, [query, endpoint, debounceMs]);

  const handleSelect = useCallback(
    (id: string) => {
      toggleSelect(id);
      setOpen(false);
    },
    [toggleSelect]
  );

  const showPopover = open && (query.trim().length > 0 || loading);

  const shortcut = useMemo(() => {
    if (typeof navigator === "undefined") return "⌘K";
    return /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘K" : "Ctrl+K";
  }, []);

  return (
    <Popover.Root open={showPopover} onOpenChange={setOpen}>
      <Popover.Anchor asChild>
        <div className="relative w-full">
          <input
            ref={inputRef}
            type="text"
            role="searchbox"
            aria-label="Search entities"
            placeholder={`Search entities… (${shortcut})`}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (!open) setOpen(true);
            }}
            onFocus={() => {
              if (query.trim()) setOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 pr-16 text-sm font-mono tracking-tight text-slate-900 shadow-sm outline-none transition focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
          <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
            {shortcut}
          </kbd>
        </div>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          onOpenAutoFocus={(e) => e.preventDefault()}
          onEscapeKeyDown={() => setOpen(false)}
          className="z-50 max-h-[360px] w-[var(--radix-popover-trigger-width)] min-w-[320px] overflow-y-auto rounded-md border border-slate-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900"
        >
          {loading && (
            <div
              role="status"
              className="px-3 py-2 text-xs uppercase tracking-wider text-slate-500"
            >
              Searching…
            </div>
          )}
          {error && !loading && (
            <div role="alert" className="px-3 py-2 text-xs text-red-600">
              {error}
            </div>
          )}
          {!loading && !error && results.length === 0 && query.trim() && (
            <div className="px-3 py-2 text-xs text-slate-500">No matches.</div>
          )}
          <ul role="listbox" className="space-y-0.5">
            {results.map((r) => (
              <li key={r.id}>
                <div
                  role="option"
                  aria-selected={false}
                  tabIndex={0}
                  onClick={() => handleSelect(r.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSelect(r.id);
                    }
                  }}
                  className="group flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-100 focus:bg-slate-100 focus:outline-none dark:hover:bg-slate-800 dark:focus:bg-slate-800"
                >
                  <span
                    aria-hidden
                    className="grid h-6 w-6 flex-none place-items-center rounded text-xs"
                    style={{
                      backgroundColor: `${layerColor(r.layer)}1a`,
                      color: layerColor(r.layer),
                    }}
                  >
                    {TYPE_GLYPH[r.type] ?? "•"}
                  </span>
                  <span className="flex-1 truncate font-medium text-slate-900 dark:text-slate-100">
                    {r.name}
                  </span>
                  <span
                    className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                    style={{
                      backgroundColor: `${layerColor(r.layer)}1a`,
                      color: layerColor(r.layer),
                    }}
                  >
                    {r.layer}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelect(r.id);
                    }}
                    className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 opacity-0 transition group-hover:opacity-100 hover:bg-slate-900 hover:text-white dark:border-slate-600 dark:text-slate-300"
                  >
                    Add to selection
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export default GraphSearchBar;
