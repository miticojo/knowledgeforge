/**
 * Tests for <GlossaryTooltip /> — Radix UI tooltip wrapper that surfaces
 * definitions for technical terms on hover/focus.
 */
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { GlossaryTooltip } from "@/components/GlossaryTooltip";

describe("GlossaryTooltip", () => {
  it("renders children with an interactive tooltip trigger when the term is in the glossary", () => {
    render(
      <GlossaryTooltip term="RRF">
        <span>RRF</span>
      </GlossaryTooltip>
    );

    const trigger = screen.getByText("RRF");
    expect(trigger).toBeInTheDocument();
    // Trigger element gets the cursor-help styling indicating it's wrapped.
    const wrapper = trigger.closest("span[tabindex='0']");
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveClass("cursor-help");
  });

  it("renders children as plain text when the term is unknown", () => {
    const { container } = render(
      <GlossaryTooltip term="DefinitelyNotAThing">
        <span>plain term</span>
      </GlossaryTooltip>
    );

    expect(screen.getByText("plain term")).toBeInTheDocument();
    // No tabindex wrapper, no Radix trigger.
    expect(container.querySelector("span[tabindex='0']")).toBeNull();
  });

  it("shows the definition in the tooltip content on focus", async () => {
    const user = userEvent.setup();
    render(
      <GlossaryTooltip term="GraphRAG">
        <span>GraphRAG</span>
      </GlossaryTooltip>
    );

    const trigger = screen.getByText("GraphRAG").closest("span[tabindex='0']")!;
    await user.tab();
    // Trigger should be focused after tab.
    expect(trigger).toHaveFocus();

    await waitFor(() => {
      // Radix renders content into a portal; query by definition substring.
      const definitions = screen.getAllByText(/knowledge graph/i);
      expect(definitions.length).toBeGreaterThan(0);
    });
  });
});
