import { create } from "zustand";

export type ArchimateLayer =
  | "Strategy"
  | "Business"
  | "Application"
  | "Technology"
  | "Motivation";

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  layer: ArchimateLayer | string;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  type: string;
  confidence?: number;
}

export interface GraphFilters {
  layers: string[];
  types: string[];
  confidences: string[];
  documentId?: string;
}

export interface GraphSubGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center_id?: string;
}

export interface GraphStoreState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  filters: GraphFilters;
  selection: Set<string>;
  isLoading: boolean;
  error?: string;
  scope: string[];

  setNodes: (nodes: GraphNode[]) => void;
  setEdges: (edges: GraphEdge[]) => void;
  mergeSubGraph: (sub: GraphSubGraph) => void;
  toggleSelect: (id: string) => void;
  selectMany: (ids: string[]) => void;
  clearSelection: () => void;
  setScope: (ids: string[]) => void;
  clearScope: () => void;
  setFilters: (partial: Partial<GraphFilters>) => void;
  resetFilters: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error?: string) => void;
}

const DEFAULT_FILTERS: GraphFilters = {
  layers: [],
  types: [],
  confidences: [],
  documentId: undefined,
};

export const useGraphStore = create<GraphStoreState>((set) => ({
  nodes: [],
  edges: [],
  filters: { ...DEFAULT_FILTERS },
  selection: new Set<string>(),
  isLoading: false,
  error: undefined,
  scope: [],

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  mergeSubGraph: (sub) =>
    set((state) => {
      const nodeIds = new Set(state.nodes.map((n) => n.id));
      const newNodes = [...state.nodes];
      for (const raw of sub.nodes || []) {
        // Normalize backend (entity_id) -> store (id)
        const n: GraphNode = {
          id: (raw as any).id || (raw as any).entity_id,
          type: raw.type,
          name: raw.name,
          layer: raw.layer,
        };
        if (n.id && !nodeIds.has(n.id)) {
          newNodes.push(n);
          nodeIds.add(n.id);
        }
      }
      const edgeKey = (e: GraphEdge) => `${e.source_id}|${e.target_id}|${e.type}`;
      const edgeKeys = new Set(state.edges.map(edgeKey));
      const newEdges = [...state.edges];
      for (const e of sub.edges || []) {
        const k = edgeKey(e);
        if (!edgeKeys.has(k)) {
          newEdges.push(e);
          edgeKeys.add(k);
        }
      }
      return { nodes: newNodes, edges: newEdges };
    }),

  toggleSelect: (id) =>
    set((state) => {
      const next = new Set(state.selection);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { selection: next };
    }),

  selectMany: (ids) =>
    set((state) => {
      const next = new Set(state.selection);
      for (const id of ids) next.add(id);
      return { selection: next };
    }),

  clearSelection: () => set({ selection: new Set<string>() }),

  setScope: (ids) => set({ scope: ids }),

  clearScope: () => set({ scope: [] }),

  setFilters: (partial) =>
    set((state) => ({ filters: { ...state.filters, ...partial } })),

  resetFilters: () => set({ filters: { ...DEFAULT_FILTERS } }),

  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
}));
