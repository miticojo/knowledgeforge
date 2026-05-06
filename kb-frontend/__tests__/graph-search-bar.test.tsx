import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GraphSearchBar } from "@/components/graph/GraphSearchBar";
import { useGraphStore } from "@/lib/graph-store";

function mockFetch(payload: unknown, ok = true) {
  const fn = vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: async () => payload,
  });
  global.fetch = fn as unknown as typeof fetch;
  return fn;
}

describe("GraphSearchBar", () => {
  beforeEach(() => {
    useGraphStore.setState({ selection: new Set<string>() });
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens popover and calls debounced fetch on typing", async () => {
    const fetchMock = mockFetch([
      { id: "n1", name: "Customer", type: "BusinessActor", layer: "Business" },
    ]);
    const user = userEvent.setup();
    render(<GraphSearchBar debounceMs={50} />);

    const input = screen.getByRole("searchbox", { name: /search entities/i });
    await user.type(input, "cust");

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("q=cust");
    expect(calledUrl).toContain("limit=20");

    expect(await screen.findByRole("option", { name: /Customer/ })).toBeInTheDocument();
  });

  it("opens popover via Cmd+K and focuses input", async () => {
    mockFetch([]);
    const user = userEvent.setup();
    render(<GraphSearchBar />);
    const input = screen.getByRole("searchbox", { name: /search entities/i });

    await user.keyboard("{Meta>}k{/Meta}");
    expect(document.activeElement).toBe(input);
  });

  it("clicking a result toggles selection in the store", async () => {
    mockFetch([
      { id: "n42", name: "Order", type: "BusinessObject", layer: "Business" },
    ]);
    const user = userEvent.setup();
    render(<GraphSearchBar debounceMs={20} />);

    const input = screen.getByRole("searchbox", { name: /search entities/i });
    await user.type(input, "ord");

    const opt = await screen.findByRole("option", { name: /Order/ });
    await user.click(opt);

    expect(useGraphStore.getState().selection.has("n42")).toBe(true);
  });
});
