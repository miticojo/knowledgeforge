import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GraphFilterSidebar } from "@/components/graph/GraphFilterSidebar";
import { useGraphStore } from "@/lib/graph-store";
import { ENTITY_TYPES_BY_LAYER } from "@/lib/archimate";

function mockDocsFetch(docs: { id: string; name: string }[]) {
  const fn = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => docs,
  });
  global.fetch = fn as unknown as typeof fetch;
  return fn;
}

beforeEach(() => {
  useGraphStore.getState().resetFilters();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("GraphFilterSidebar", () => {
  it("toggling a layer auto-checks its entity types in the store", async () => {
    mockDocsFetch([]);
    const user = userEvent.setup();
    render(<GraphFilterSidebar />);

    const cb = screen.getByRole("checkbox", { name: /Layer Business/i });
    await user.click(cb);

    const state = useGraphStore.getState();
    expect(state.filters.layers).toContain("Business");
    for (const t of ENTITY_TYPES_BY_LAYER.Business) {
      expect(state.filters.types).toContain(t);
    }
  });

  it("expands the entity-type accordion for a layer", async () => {
    mockDocsFetch([]);
    const user = userEvent.setup();
    render(<GraphFilterSidebar />);

    const trigger = screen.getByRole("button", {
      name: /Application/i,
      expanded: false,
    });
    await user.click(trigger);

    expect(
      screen.getByRole("checkbox", { name: /Entity type ApplicationComponent/ })
    ).toBeInTheDocument();
  });

  it("confidence radio updates store confidences set", async () => {
    mockDocsFetch([]);
    const user = userEvent.setup();
    render(<GraphFilterSidebar />);

    await user.click(screen.getByRole("radio", { name: /EXTRACTED only/i }));
    expect(useGraphStore.getState().filters.confidences).toEqual(["EXTRACTED"]);

    await user.click(screen.getByRole("radio", { name: /^All$/i }));
    expect(useGraphStore.getState().filters.confidences).toEqual([]);
  });

  it("document picker filters and selects a document", async () => {
    mockDocsFetch([
      { id: "d1", name: "Architecture Vision" },
      { id: "d2", name: "Risk Register" },
    ]);
    const user = userEvent.setup();
    render(<GraphFilterSidebar />);

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());

    const combo = screen.getByRole("combobox", { name: /document/i });
    await user.click(combo);
    await user.type(combo, "risk");

    const opt = await screen.findByRole("option", { name: /Risk Register/i });
    await user.click(opt);

    expect(useGraphStore.getState().filters.documentId).toBe("d2");
  });

  it("reset button clears all filter state", async () => {
    mockDocsFetch([]);
    const user = userEvent.setup();
    render(<GraphFilterSidebar />);

    await user.click(screen.getByRole("checkbox", { name: /Layer Strategy/i }));
    expect(useGraphStore.getState().filters.layers.length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /^Reset$/i }));
    const f = useGraphStore.getState().filters;
    expect(f.layers).toEqual([]);
    expect(f.types).toEqual([]);
    expect(f.confidences).toEqual([]);
    expect(f.documentId).toBeUndefined();
  });
});
