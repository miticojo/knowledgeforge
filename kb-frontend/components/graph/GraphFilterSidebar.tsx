"use client";

import { useEffect, useMemo, useState } from "react";
import { useGraphStore } from "@/lib/graph-store";
import {
  CONFIDENCE_OPTIONS,
  ENTITY_TYPES_BY_LAYER,
  LAYERS,
  LAYER_COLORS,
  type ConfidenceOption,
  type Layer,
} from "@/lib/archimate";

interface DocumentItem {
  id: string;
  name: string;
}

interface GraphFilterSidebarProps {
  documentsEndpoint?: string;
}

// Map our radio choices onto the store's `confidences: string[]` shape.
const CONFIDENCE_VALUE_TO_SET: Record<ConfidenceOption, string[]> = {
  all: [],
  extracted: ["EXTRACTED"],
  extracted_inferred: ["EXTRACTED", "INFERRED"],
  all_with_ambiguous: ["EXTRACTED", "INFERRED", "AMBIGUOUS"],
};

function setEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  for (const x of b) if (!s.has(x)) return false;
  return true;
}

function inferConfidenceOption(arr: string[]): ConfidenceOption {
  for (const opt of CONFIDENCE_OPTIONS) {
    if (setEqual(arr, CONFIDENCE_VALUE_TO_SET[opt.value])) return opt.value;
  }
  return "all";
}

export function GraphFilterSidebar({
  documentsEndpoint = "/api/graph/documents",
}: GraphFilterSidebarProps) {
  const filters = useGraphStore((s) => s.filters);
  const setFilters = useGraphStore((s) => s.setFilters);
  const resetFilters = useGraphStore((s) => s.resetFilters);

  const [openLayers, setOpenLayers] = useState<Record<Layer, boolean>>(() => {
    const o = {} as Record<Layer, boolean>;
    for (const l of LAYERS) o[l] = false;
    return o;
  });

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [docQuery, setDocQuery] = useState("");
  const [docOpen, setDocOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(documentsEndpoint)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (cancelled) return;
        const list: DocumentItem[] = Array.isArray(data)
          ? data
          : Array.isArray(data?.documents)
          ? data.documents
          : [];
        setDocuments(list);
      })
      .catch(() => {
        if (!cancelled) setDocuments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [documentsEndpoint]);

  const selectedDoc = useMemo(
    () => documents.find((d) => d.id === filters.documentId) ?? null,
    [documents, filters.documentId]
  );

  const filteredDocs = useMemo(() => {
    const q = docQuery.trim().toLowerCase();
    if (!q) return documents.slice(0, 20);
    return documents
      .filter((d) => d.name.toLowerCase().includes(q))
      .slice(0, 20);
  }, [docQuery, documents]);

  const confidenceValue = inferConfidenceOption(filters.confidences);

  // Layer checkbox toggles layer + bulk-toggles its types.
  const onToggleLayer = (layer: Layer) => {
    const has = filters.layers.includes(layer);
    const types = ENTITY_TYPES_BY_LAYER[layer];
    if (has) {
      setFilters({
        layers: filters.layers.filter((l) => l !== layer),
        types: filters.types.filter((t) => !types.includes(t)),
      });
    } else {
      const merged = Array.from(new Set([...filters.types, ...types]));
      setFilters({ layers: [...filters.layers, layer], types: merged });
    }
  };

  const onToggleType = (type: string) => {
    const has = filters.types.includes(type);
    setFilters({
      types: has
        ? filters.types.filter((t) => t !== type)
        : [...filters.types, type],
    });
  };

  const onConfidence = (v: ConfidenceOption) => {
    setFilters({ confidences: CONFIDENCE_VALUE_TO_SET[v] });
  };

  const onPickDoc = (id: string | null) => {
    setFilters({ documentId: id ?? undefined });
    setDocOpen(false);
    setDocQuery("");
  };

  return (
    <aside
      aria-label="Graph filters"
      className="flex h-full w-72 flex-col gap-5 overflow-y-auto border-r border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-950"
    >
      <header className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Filters
        </h2>
        <button
          type="button"
          onClick={resetFilters}
          className="rounded border border-slate-300 px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-900 hover:text-white dark:border-slate-700 dark:text-slate-300"
        >
          Reset
        </button>
      </header>

      {/* Layers */}
      <section aria-labelledby="filter-layer-heading">
        <h3
          id="filter-layer-heading"
          className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500"
        >
          Layer
        </h3>
        <ul className="space-y-1">
          {LAYERS.map((layer) => {
            const checked = filters.layers.includes(layer);
            return (
              <li key={layer}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-slate-50 dark:hover:bg-slate-900">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggleLayer(layer)}
                    aria-label={`Layer ${layer}`}
                    className="h-3.5 w-3.5 accent-slate-900"
                  />
                  <span
                    aria-hidden
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: LAYER_COLORS[layer] }}
                  />
                  <span className="text-slate-800 dark:text-slate-200">
                    {layer}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </section>

      {/* Entity types accordion */}
      <section aria-labelledby="filter-type-heading">
        <h3
          id="filter-type-heading"
          className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500"
        >
          Entity type
        </h3>
        <ul className="space-y-1">
          {LAYERS.map((layer) => {
            const expanded = openLayers[layer];
            const types = ENTITY_TYPES_BY_LAYER[layer];
            return (
              <li
                key={layer}
                className="rounded border border-slate-200 dark:border-slate-800"
              >
                <button
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={`type-group-${layer}`}
                  onClick={() =>
                    setOpenLayers((o) => ({ ...o, [layer]: !o[layer] }))
                  }
                  className="flex w-full items-center justify-between px-2 py-1.5 text-left"
                >
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: LAYER_COLORS[layer] }}
                    />
                    <span className="text-xs font-semibold tracking-wide text-slate-700 dark:text-slate-300">
                      {layer}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      ({types.length})
                    </span>
                  </span>
                  <span
                    aria-hidden
                    className="text-xs text-slate-400"
                  >
                    {expanded ? "−" : "+"}
                  </span>
                </button>
                {expanded && (
                  <ul
                    id={`type-group-${layer}`}
                    className="border-t border-slate-100 px-2 py-1 dark:border-slate-800"
                  >
                    {types.map((t) => {
                      const checked = filters.types.includes(t);
                      return (
                        <li key={t}>
                          <label className="flex cursor-pointer items-center gap-2 py-0.5 text-xs">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => onToggleType(t)}
                              aria-label={`Entity type ${t}`}
                              className="h-3 w-3 accent-slate-900"
                            />
                            <span className="text-slate-700 dark:text-slate-300">
                              {t}
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {/* Confidence */}
      <section aria-labelledby="filter-confidence-heading" role="radiogroup">
        <h3
          id="filter-confidence-heading"
          className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500"
        >
          Confidence
        </h3>
        <ul className="space-y-1">
          {CONFIDENCE_OPTIONS.map((opt) => (
            <li key={opt.value}>
              <label className="flex cursor-pointer items-center gap-2 text-xs">
                <input
                  type="radio"
                  name="graph-confidence"
                  value={opt.value}
                  checked={confidenceValue === opt.value}
                  onChange={() => onConfidence(opt.value)}
                  aria-label={opt.label}
                  className="h-3.5 w-3.5 accent-slate-900"
                />
                <span className="text-slate-800 dark:text-slate-200">
                  {opt.label}
                </span>
              </label>
            </li>
          ))}
        </ul>
      </section>

      {/* Document picker */}
      <section aria-labelledby="filter-doc-heading">
        <h3
          id="filter-doc-heading"
          className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500"
        >
          Document
        </h3>
        <div className="relative">
          <input
            type="text"
            role="combobox"
            aria-expanded={docOpen}
            aria-controls="document-picker-list"
            aria-label="Filter by document"
            placeholder={selectedDoc ? selectedDoc.name : "Any document"}
            value={docQuery}
            onChange={(e) => {
              setDocQuery(e.target.value);
              setDocOpen(true);
            }}
            onFocus={() => setDocOpen(true)}
            onBlur={() => window.setTimeout(() => setDocOpen(false), 120)}
            className="w-full rounded border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
          {selectedDoc && (
            <button
              type="button"
              onClick={() => onPickDoc(null)}
              className="absolute right-1 top-1/2 -translate-y-1/2 rounded px-1 text-[10px] text-slate-500 hover:text-slate-900 dark:hover:text-white"
              aria-label="Clear document filter"
            >
              Any
            </button>
          )}
          {docOpen && filteredDocs.length > 0 && (
            <ul
              id="document-picker-list"
              role="listbox"
              className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900"
            >
              {filteredDocs.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={filters.documentId === d.id}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      onPickDoc(d.id);
                    }}
                    className="block w-full truncate px-2 py-1 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-800"
                  >
                    {d.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </aside>
  );
}

export default GraphFilterSidebar;
