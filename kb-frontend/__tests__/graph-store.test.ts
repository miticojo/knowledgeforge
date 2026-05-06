import { beforeEach, describe, expect, it } from "vitest";
import { useGraphStore } from "@/lib/graph-store";

describe("graph-store", () => {
  beforeEach(() => {
    useGraphStore.setState({
      nodes: [],
      edges: [],
      filters: { layers: [], types: [], confidences: [], documentId: undefined },
      selection: new Set<string>(),
      isLoading: false,
      error: undefined,
      scope: [],
    });
  });

  it("toggleSelect adds and removes ids", () => {
    const { toggleSelect } = useGraphStore.getState();
    toggleSelect("a");
    expect(useGraphStore.getState().selection.has("a")).toBe(true);
    toggleSelect("a");
    expect(useGraphStore.getState().selection.has("a")).toBe(false);
  });

  it("selectMany merges into selection", () => {
    useGraphStore.getState().toggleSelect("a");
    useGraphStore.getState().selectMany(["b", "c", "a"]);
    const sel = useGraphStore.getState().selection;
    expect(sel.size).toBe(3);
    expect(sel.has("a")).toBe(true);
    expect(sel.has("b")).toBe(true);
    expect(sel.has("c")).toBe(true);
  });

  it("clearSelection empties selection", () => {
    useGraphStore.getState().selectMany(["a", "b"]);
    useGraphStore.getState().clearSelection();
    expect(useGraphStore.getState().selection.size).toBe(0);
  });

  it("mergeSubGraph dedupes nodes and edges", () => {
    useGraphStore.setState({
      nodes: [{ id: "n1", type: "T", name: "One", layer: "Business" }],
      edges: [{ source_id: "n1", target_id: "n2", type: "rel" }],
    });
    useGraphStore.getState().mergeSubGraph({
      nodes: [
        { id: "n1", type: "T", name: "One", layer: "Business" }, // duplicate
        { id: "n2", type: "T", name: "Two", layer: "Application" }, // new
      ],
      edges: [
        { source_id: "n1", target_id: "n2", type: "rel" }, // duplicate
        { source_id: "n2", target_id: "n3", type: "rel2" }, // new
      ],
    });
    const { nodes, edges } = useGraphStore.getState();
    expect(nodes.map((n) => n.id).sort()).toEqual(["n1", "n2"]);
    expect(edges).toHaveLength(2);
  });

  it("setFilters merges partial and resetFilters restores defaults", () => {
    useGraphStore.getState().setFilters({ layers: ["Business"], documentId: "d1" });
    expect(useGraphStore.getState().filters.layers).toEqual(["Business"]);
    expect(useGraphStore.getState().filters.documentId).toBe("d1");
    useGraphStore.getState().setFilters({ types: ["BusinessActor"] });
    expect(useGraphStore.getState().filters.layers).toEqual(["Business"]);
    expect(useGraphStore.getState().filters.types).toEqual(["BusinessActor"]);
    useGraphStore.getState().resetFilters();
    expect(useGraphStore.getState().filters).toEqual({
      layers: [],
      types: [],
      confidences: [],
      documentId: undefined,
    });
  });

  it("setScope updates scope ids", () => {
    useGraphStore.getState().setScope(["a", "b"]);
    expect(useGraphStore.getState().scope).toEqual(["a", "b"]);
  });
});
