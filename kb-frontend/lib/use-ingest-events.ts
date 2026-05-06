"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type IngestStatus = "idle" | "running" | "complete" | "failed";

export type FileStatus = "routed" | "parsing" | "done" | "failed";

export interface LayerBreakdown {
  [layer: string]: number;
}

export interface ConfidenceBreakdown {
  EXTRACTED: number;
  INFERRED: number;
  AMBIGUOUS: number;
}

export interface EntityLite {
  id: string;
  type: string;
  name: string;
  layer: string;
  confidence: string;
}

export interface EdgeLite {
  source: string;
  target: string;
  rel: string;
  confidence: string;
}

export interface FileSummary {
  file: string;
  parser: string;
  status: FileStatus;
  reason?: string;
  entities: number;
  edges: number;
  layer_breakdown: LayerBreakdown;
  confidence_breakdown: ConfidenceBreakdown;
  duration_ms: number;
  error?: string;
  entitiesList?: EntityLite[];
  edgesList?: EdgeLite[];
  truncated?: boolean;
}

export interface AccumulatedGraph {
  entities: EntityLite[];
  edges: EdgeLite[];
}

const ENTITY_CAP = 1500;

export interface IngestTotals {
  files_processed: number;
  files_failed: number;
  total_entities: number;
  total_edges: number;
  duration_ms: number;
}

export interface IngestEvent {
  name: string;
  data: Record<string, unknown>;
  ts: number;
}

export interface IngestEventsState {
  events: IngestEvent[];
  status: IngestStatus;
  fileSummaries: FileSummary[];
  totals: IngestTotals;
  writePhase: "pending" | "writing" | "done";
  accumulated: AccumulatedGraph;
}

const EMPTY_TOTALS: IngestTotals = {
  files_processed: 0,
  files_failed: 0,
  total_entities: 0,
  total_edges: 0,
  duration_ms: 0,
};

const EMPTY_CONFIDENCE: ConfidenceBreakdown = {
  EXTRACTED: 0,
  INFERRED: 0,
  AMBIGUOUS: 0,
};

function emptyState(): IngestEventsState {
  return {
    events: [],
    status: "idle",
    fileSummaries: [],
    totals: { ...EMPTY_TOTALS },
    writePhase: "pending",
    accumulated: { entities: [], edges: [] },
  };
}

function edgeKey(e: EdgeLite): string {
  return `${e.source}->${e.rel}->${e.target}`;
}

export function useIngestEvents(jobId: string | null): IngestEventsState {
  const [state, setState] = useState<IngestEventsState>(emptyState);
  const fileMapRef = useRef<Map<string, FileSummary>>(new Map());
  const entityIdsRef = useRef<Set<string>>(new Set());
  const edgeKeysRef = useRef<Set<string>>(new Set());
  const accumulatedRef = useRef<AccumulatedGraph>({ entities: [], edges: [] });

  useEffect(() => {
    if (!jobId) {
      fileMapRef.current = new Map();
      entityIdsRef.current = new Set();
      edgeKeysRef.current = new Set();
      accumulatedRef.current = { entities: [], edges: [] };
      setState(emptyState());
      return;
    }

    fileMapRef.current = new Map();
    entityIdsRef.current = new Set();
    edgeKeysRef.current = new Set();
    accumulatedRef.current = { entities: [], edges: [] };
    setState({ ...emptyState(), status: "running" });

    const url = `/api/ingest/${encodeURIComponent(jobId)}/events`;
    const es = new EventSource(url);

    const pushEvent = (name: string, data: Record<string, unknown>) => {
      setState((prev) => ({
        ...prev,
        events: [...prev.events, { name, data, ts: Date.now() }],
      }));
    };

    const upsertFile = (
      file: string,
      patch: Partial<FileSummary>
    ): FileSummary => {
      const existing = fileMapRef.current.get(file);
      const next: FileSummary = {
        file,
        parser: existing?.parser ?? "",
        status: existing?.status ?? "routed",
        reason: existing?.reason,
        entities: existing?.entities ?? 0,
        edges: existing?.edges ?? 0,
        layer_breakdown: existing?.layer_breakdown ?? {},
        confidence_breakdown: existing?.confidence_breakdown ?? { ...EMPTY_CONFIDENCE },
        duration_ms: existing?.duration_ms ?? 0,
        error: existing?.error,
        ...patch,
      };
      fileMapRef.current.set(file, next);
      return next;
    };

    const commitSummaries = () => {
      setState((prev) => ({
        ...prev,
        fileSummaries: Array.from(fileMapRef.current.values()),
      }));
    };

    const handle = (name: string, raw: string) => {
      let data: Record<string, unknown> = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        data = { raw };
      }
      pushEvent(name, data);

      switch (name) {
        case "route": {
          const file = String(data.file ?? "");
          if (!file) break;
          upsertFile(file, {
            parser: String(data.parser ?? ""),
            reason: data.reason ? String(data.reason) : undefined,
            status: "routed",
          });
          commitSummaries();
          break;
        }
        case "parse_start": {
          const file = String(data.file ?? "");
          if (!file) break;
          upsertFile(file, {
            parser: String(data.parser ?? ""),
            status: "parsing",
          });
          commitSummaries();
          break;
        }
        case "parse_end": {
          const file = String(data.file ?? "");
          if (!file) break;
          const entities = Number(data.entities_added ?? 0);
          const edges = Number(data.edges_added ?? 0);
          const duration = Number(data.duration_ms ?? 0);
          const entitiesList = Array.isArray(data.entities)
            ? (data.entities as EntityLite[])
            : undefined;
          const edgesList = Array.isArray(data.edges)
            ? (data.edges as EdgeLite[])
            : undefined;
          const truncated = Boolean(data.truncated);
          upsertFile(file, {
            parser: String(data.parser ?? ""),
            status: "done",
            entities,
            edges,
            layer_breakdown: (data.layer_breakdown as LayerBreakdown) ?? {},
            confidence_breakdown:
              (data.confidence_breakdown as ConfidenceBreakdown) ?? { ...EMPTY_CONFIDENCE },
            duration_ms: duration,
            entitiesList,
            edgesList,
            truncated,
          });

          // Accumulate union, deduped, capped.
          if (entitiesList) {
            for (const ent of entitiesList) {
              if (!ent || !ent.id) continue;
              if (entityIdsRef.current.has(ent.id)) continue;
              if (accumulatedRef.current.entities.length >= ENTITY_CAP) break;
              entityIdsRef.current.add(ent.id);
              accumulatedRef.current.entities.push(ent);
            }
          }
          if (edgesList) {
            for (const edge of edgesList) {
              if (!edge || !edge.source || !edge.target) continue;
              const key = edgeKey(edge);
              if (edgeKeysRef.current.has(key)) continue;
              edgeKeysRef.current.add(key);
              accumulatedRef.current.edges.push(edge);
            }
          }

          setState((prev) => ({
            ...prev,
            fileSummaries: Array.from(fileMapRef.current.values()),
            accumulated: {
              entities: [...accumulatedRef.current.entities],
              edges: [...accumulatedRef.current.edges],
            },
            totals: {
              ...prev.totals,
              files_processed: prev.totals.files_processed + 1,
              total_entities: prev.totals.total_entities + entities,
              total_edges: prev.totals.total_edges + edges,
            },
          }));
          break;
        }
        case "parse_error": {
          const file = String(data.file ?? "");
          if (!file) break;
          upsertFile(file, {
            parser: String(data.parser ?? ""),
            status: "failed",
            error: String(data.error ?? "Unknown error"),
          });
          setState((prev) => ({
            ...prev,
            fileSummaries: Array.from(fileMapRef.current.values()),
            totals: {
              ...prev.totals,
              files_failed: prev.totals.files_failed + 1,
            },
          }));
          break;
        }
        case "write_start": {
          setState((prev) => ({ ...prev, writePhase: "writing" }));
          break;
        }
        case "write_end": {
          const totalEntities = Number(data.total_entities ?? 0);
          const totalEdges = Number(data.total_edges ?? 0);
          const duration = Number(data.duration_ms ?? 0);
          setState((prev) => ({
            ...prev,
            writePhase: "done",
            totals: {
              ...prev.totals,
              total_entities: totalEntities || prev.totals.total_entities,
              total_edges: totalEdges || prev.totals.total_edges,
              duration_ms: duration || prev.totals.duration_ms,
            },
          }));
          break;
        }
        case "complete": {
          setState((prev) => ({ ...prev, status: "complete" }));
          es.close();
          break;
        }
        case "failed": {
          setState((prev) => ({ ...prev, status: "failed" }));
          es.close();
          break;
        }
      }
    };

    const named = [
      "route",
      "parse_start",
      "parse_end",
      "parse_error",
      "write_start",
      "write_end",
      "complete",
      "failed",
    ];
    const listeners: Array<[string, (e: MessageEvent) => void]> = named.map((n) => {
      const fn = (e: MessageEvent) => handle(n, e.data);
      es.addEventListener(n, fn as EventListener);
      return [n, fn];
    });

    const onError = () => {
      // Browser will retry automatically on transient errors. Only flip to
      // failed if we have not yet completed and the connection is closed.
      if (es.readyState === EventSource.CLOSED) {
        setState((prev) =>
          prev.status === "running" ? { ...prev, status: "failed" } : prev
        );
      }
    };
    es.addEventListener("error", onError);

    return () => {
      for (const [n, fn] of listeners) {
        es.removeEventListener(n, fn as EventListener);
      }
      es.removeEventListener("error", onError);
      es.close();
    };
  }, [jobId]);

  // Stable view: reorder file summaries so failed/parsing rows surface first.
  return useMemo(() => state, [state]);
}
