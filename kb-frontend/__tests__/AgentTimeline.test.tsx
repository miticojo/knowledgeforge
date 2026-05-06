import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AgentTimeline from "@/components/ingestion/AgentTimeline";
import type { IngestEventsState } from "@/lib/use-ingest-events";

function buildState(): IngestEventsState {
  return {
    events: [],
    status: "running",
    writePhase: "pending",
    fileSummaries: [
      {
        file: "src/app/main.py",
        parser: "python-ast",
        status: "done",
        entities: 12,
        edges: 18,
        layer_breakdown: { Application: 9, Technology: 3 },
        confidence_breakdown: { EXTRACTED: 10, INFERRED: 2, AMBIGUOUS: 0 },
        duration_ms: 145,
      },
      {
        file: "docs/architecture.md",
        parser: "gemini-markdown",
        status: "parsing",
        entities: 0,
        edges: 0,
        layer_breakdown: {},
        confidence_breakdown: { EXTRACTED: 0, INFERRED: 0, AMBIGUOUS: 0 },
        duration_ms: 0,
      },
      {
        file: "db/schema.sql",
        parser: "sqlglot",
        status: "failed",
        entities: 0,
        edges: 0,
        layer_breakdown: {},
        confidence_breakdown: { EXTRACTED: 0, INFERRED: 0, AMBIGUOUS: 0 },
        duration_ms: 12,
        error: "ParseError: unexpected token",
      },
    ],
    totals: {
      files_processed: 1,
      files_failed: 1,
      total_entities: 12,
      total_edges: 18,
      duration_ms: 157,
    },
    accumulated: { entities: [], edges: [] },
  };
}

describe("AgentTimeline", () => {
  it("renders rows for each file with parser badges and counts", () => {
    render(<AgentTimeline state={buildState()} />);

    expect(screen.getByText("src/app/main.py")).toBeInTheDocument();
    expect(screen.getByText("docs/architecture.md")).toBeInTheDocument();
    expect(screen.getByText("db/schema.sql")).toBeInTheDocument();

    expect(screen.getByText("python-ast")).toBeInTheDocument();
    expect(screen.getByText("gemini-markdown")).toBeInTheDocument();
    expect(screen.getByText("sqlglot")).toBeInTheDocument();

    // Entity / edge chips for the completed row.
    expect(screen.getByText("12 ent")).toBeInTheDocument();
    expect(screen.getByText("18 edg")).toBeInTheDocument();

    // Totals counters.
    expect(screen.getByText("Entities")).toBeInTheDocument();
    expect(screen.getByText("Edges")).toBeInTheDocument();

    // Failure error preview should surface.
    expect(screen.getByText(/ParseError: unexpected token/)).toBeInTheDocument();

    // Footer summary line.
    expect(screen.getByText(/1 processed/)).toBeInTheDocument();
  });
});
