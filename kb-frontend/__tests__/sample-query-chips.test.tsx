import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SampleQueryChips, SAMPLE_QUERIES } from "@/components/SampleQueryChips";

describe("SampleQueryChips", () => {
  it("renders all six sample query chips", () => {
    render(<SampleQueryChips onSelect={() => {}} />);
    expect(SAMPLE_QUERIES).toHaveLength(6);
    for (const q of SAMPLE_QUERIES) {
      expect(screen.getByRole("button", { name: new RegExp(escapeRegex(q)) })).toBeInTheDocument();
    }
  });

  it("invokes onSelect with the chip's query text on click", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<SampleQueryChips onSelect={onSelect} />);

    const target = SAMPLE_QUERIES[2];
    await user.click(screen.getByRole("button", { name: new RegExp(escapeRegex(target)) }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(target);
  });

  it("disables all chips when disabled prop is true", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<SampleQueryChips onSelect={onSelect} disabled />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(SAMPLE_QUERIES.length);
    for (const b of buttons) {
      expect(b).toBeDisabled();
    }
    await user.click(buttons[0]);
    expect(onSelect).not.toHaveBeenCalled();
  });
});

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
