/**
 * Tests for the Welcome / landing page.
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import WelcomePage from "@/app/welcome/page";

describe("WelcomePage", () => {
  it("renders the hero headline", () => {
    render(<WelcomePage />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toBeInTheDocument();
    expect(heading).toHaveTextContent(/KnowledgeForge/i);
    expect(heading).toHaveTextContent(/AgenticRAG over GraphRAG/i);
    expect(heading).toHaveTextContent(/Google Cloud/i);
  });

  it("exposes both hero CTAs and points the demo CTA at /chat?prompt=", () => {
    render(<WelcomePage />);

    const demo = screen.getByRole("link", { name: /try a demo query/i });
    expect(demo).toBeInTheDocument();
    const demoHref = demo.getAttribute("href") ?? "";
    expect(demoHref).toContain("/chat?prompt=");

    const ingest = screen.getByRole("link", { name: /ingest a repo/i });
    expect(ingest).toBeInTheDocument();
    expect(ingest.getAttribute("href")).toBe("/ingestion");
  });

  it("renders all 4 capability cards with their titles", () => {
    render(<WelcomePage />);

    const titles = [
      "Ingest anything",
      "GraphRAG over ArchiMate 3.2",
      "AgenticRAG",
      "MCP-native",
    ];

    for (const title of titles) {
      expect(
        screen.getByRole("heading", { level: 2, name: title })
      ).toBeInTheDocument();
    }

    // Each card has a "Learn more" link
    const learnMore = screen.getAllByRole("link", { name: /learn more/i });
    expect(learnMore.length).toBe(4);
  });

  it("renders the How it works section linking to architecture, benchmark and the rag primer doc", () => {
    render(<WelcomePage />);

    const section = screen
      .getByRole("heading", { level: 2, name: /how it works/i })
      .closest("section");
    expect(section).not.toBeNull();
    const scoped = within(section as HTMLElement);

    expect(
      scoped.getByRole("link", { name: /architecture/i }).getAttribute("href")
    ).toBe("/architecture");
    expect(
      scoped.getByRole("link", { name: /benchmark/i }).getAttribute("href")
    ).toBe("/benchmark");
    expect(
      scoped.getByRole("link", { name: /rag primer/i }).getAttribute("href")
    ).toBe("/docs/concepts/rag-primer.md");
  });
});
