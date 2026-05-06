import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useGraphStore } from "@/lib/graph-store";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/graph",
}));

// Avoid loading react-force-graph-2d (canvas-heavy) in jsdom
vi.mock("@/components/graph/GraphCanvas", () => ({
  default: () => <div data-testid="graph-canvas-stub" />,
}));

import GraphPage from "@/app/graph/page";

describe("GraphPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
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

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders empty state when /api/graph/all returns 0 nodes", async () => {
    // mockImplementation → fresh Response per call. Response bodies can only be
    // read once, so a single mockResolvedValue would crash on the 2nd fetch
    // (GraphFilterSidebar / GraphSearchBar also hit /api/graph/* on mount).
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ nodes: [], edges: [], documents: [], matches: [], total_nodes: 0, total_edges: 0, has_more: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    render(<GraphPage />);

    await waitFor(() => {
      expect(screen.getByText(/No graph data yet/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: /Go to Ingestion/i })).toHaveAttribute(
      "href",
      "/ingestion"
    );
  });

  it("'Use N as chat scope' navigates to /chat?scope=...", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.includes("/api/graph/all")) {
        return new Response(
          JSON.stringify({
            nodes: [
              { id: "id1", type: "BusinessActor", name: "Alice", layer: "Business" },
              { id: "id2", type: "ApplicationComponent", name: "App", layer: "Application" },
            ],
            edges: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify({ documents: [], matches: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<GraphPage />);

    await waitFor(() => {
      expect(useGraphStore.getState().nodes).toHaveLength(2);
    });

    // simulate selection from outside the canvas
    useGraphStore.getState().selectMany(["id1", "id2"]);

    const button = await screen.findByRole("button", { name: /Use 2 as chat scope/i });
    await userEvent.click(button);

    expect(pushMock).toHaveBeenCalledWith("/chat?scope=id1,id2");
    expect(useGraphStore.getState().scope).toEqual(["id1", "id2"]);
  });

  it("renders the filter sidebar slot for T29", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ nodes: [], edges: [], documents: [], matches: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const { container } = render(<GraphPage />);
    await waitFor(() => {
      expect(container.querySelector("#filter-sidebar-slot")).toBeInTheDocument();
    });
  });
});
