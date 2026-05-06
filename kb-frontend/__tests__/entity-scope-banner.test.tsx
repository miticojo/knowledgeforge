import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EntityScopeBanner } from "@/components/EntityScopeBanner";
import { useGraphStore } from "@/lib/graph-store";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

describe("EntityScopeBanner", () => {
  beforeEach(() => {
    pushMock.mockReset();
    useGraphStore.getState().clearScope();
  });

  it("renders nothing when scope is empty", () => {
    const { container } = render(<EntityScopeBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders an entity-count label when scope has ids", () => {
    useGraphStore.getState().setScope(["a", "b", "c"]);
    render(<EntityScopeBanner />);
    expect(screen.getByText(/Filtered to 3 entities/i)).toBeInTheDocument();
  });

  it("calls clearScope when the Clear button is clicked", async () => {
    useGraphStore.getState().setScope(["a", "b"]);
    const user = userEvent.setup();
    render(<EntityScopeBanner />);

    await user.click(screen.getByRole("button", { name: /clear scope/i }));

    expect(useGraphStore.getState().scope).toEqual([]);
  });

  it("View graph navigates to /graph with the entity ids in selected param", async () => {
    useGraphStore.getState().setScope(["id1", "id2", "id3"]);
    const user = userEvent.setup();
    render(<EntityScopeBanner />);

    await user.click(screen.getByRole("button", { name: /view graph/i }));

    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/graph?selected=id1,id2,id3");
  });
});
