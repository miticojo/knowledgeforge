import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import GraphDelta from "@/components/ingestion/GraphDelta";
import type { AccumulatedGraph } from "@/lib/use-ingest-events";

vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

describe("GraphDelta", () => {
  it("renders one svg circle per entity and one line per edge", () => {
    const acc: AccumulatedGraph = {
      entities: Array.from({ length: 6 }, (_, i) => ({
        id: `e${i}`,
        name: `Entity ${i}`,
        type: "ApplicationComponent",
        layer: "Application",
        confidence: "EXTRACTED",
      })),
      edges: [
        { source: "e0", target: "e1", rel: "Composition", confidence: "EXTRACTED" },
        { source: "e1", target: "e2", rel: "Composition", confidence: "EXTRACTED" },
        { source: "e2", target: "e3", rel: "Flow", confidence: "INFERRED" },
        { source: "e3", target: "e4", rel: "Flow", confidence: "INFERRED" },
      ],
    };

    render(<GraphDelta accumulated={acc} />);

    expect(screen.getAllByTestId("gd-node")).toHaveLength(6);
    expect(screen.getAllByTestId("gd-edge")).toHaveLength(4);
    expect(
      screen.getByText(/6 nodes \/ 4 edges added in this run/i)
    ).toBeInTheDocument();
  });
});
