import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EmptyState from "@/components/EmptyState";

describe("EmptyState", () => {
  it("renders the title and body", () => {
    render(
      <EmptyState
        icon={<svg data-testid="icon" />}
        title="Nothing here"
        body="Come back later."
      />
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Come back later.")).toBeInTheDocument();
    expect(screen.getByTestId("icon")).toBeInTheDocument();
  });

  it("renders the CTA as a link when href is provided", () => {
    render(
      <EmptyState
        icon={<svg />}
        title="Title"
        body="Body"
        cta={{ label: "Open chat", href: "/chat" }}
      />
    );
    const link = screen.getByRole("link", { name: "Open chat" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/chat");
  });

  it("renders the CTA as a button when onClick is provided", async () => {
    const onClick = vi.fn();
    render(
      <EmptyState
        icon={<svg />}
        title="Title"
        body="Body"
        cta={{ label: "Do thing", onClick }}
      />
    );
    const button = screen.getByRole("button", { name: "Do thing" });
    expect(button).toBeInTheDocument();
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("renders cleanly without a CTA", () => {
    render(<EmptyState icon={<svg />} title="Empty" body="Nothing." />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
