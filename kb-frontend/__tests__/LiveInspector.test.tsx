import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import LiveInspector, {
  LiveInspectorArtifact,
} from "@/components/ingestion/LiveInspector";

vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const mdArtifact: LiveInspectorArtifact = {
  file: "docs/architecture.md",
  parser: "gemini-markdown",
  language: "markdown",
  source: "# Title\n\nA paragraph here.\n\n- item one\n- item two\n",
  parsed: { entities: [{ name: "Doc Title" }], edges: [] },
  entities: [
    { id: "ent-md-1", name: "Doc Title", type: "BusinessObject", layer: "Business", confidence: "EXTRACTED" },
  ],
  edges: [],
};

const pyArtifact: LiveInspectorArtifact = {
  file: "code/main.py",
  parser: "python-ast",
  language: "python",
  source: "def hello():\n    return 'hi'\n",
  parsed: {
    module: "main",
    classes: [{ name: "Greeter", methods: ["hello"] }],
    functions: ["hello"],
    imports: ["os"],
  },
  entities: [
    { id: "ent-py-1", name: "Greeter", type: "ApplicationComponent", layer: "Application", confidence: "EXTRACTED" },
    { id: "ent-py-2", name: "hello", type: "ApplicationService", layer: "Application", confidence: "EXTRACTED" },
  ],
  edges: [
    { source: "ent-py-1", target: "ent-py-2", rel: "Composition", confidence: "EXTRACTED" },
  ],
};

const sqlArtifact: LiveInspectorArtifact = {
  file: "db/schema.sql",
  parser: "sqlglot",
  language: "sql",
  source: "CREATE TABLE users (id INT PRIMARY KEY, name TEXT);",
  parsed: {
    tables: [
      {
        name: "users",
        columns: [{ name: "id", type: "INT" }, { name: "name", type: "TEXT" }],
        foreign_keys: [],
      },
    ],
  },
  entities: [
    { id: "ent-sql-1", name: "users", type: "DataObject", layer: "Application", confidence: "EXTRACTED" },
  ],
  edges: [],
};

const pdfArtifact: LiveInspectorArtifact = {
  file: "docs/whitepaper.pdf",
  parser: "liteparse",
  language: "pdf",
  source: "",
  parsed: {
    sections: [
      { title: "Introduction", level: 1, page: 1 },
      { title: "Background", level: 2, page: 2 },
    ],
    image_count: 4,
    page_count: 12,
  },
  entities: [
    { id: "ent-pdf-1", name: "Whitepaper", type: "BusinessObject", layer: "Business", confidence: "EXTRACTED" },
  ],
  edges: [],
};

describe("LiveInspector", () => {
  it("renders markdown artifact: source heading, parsed JSON tree, and entity chips", () => {
    render(
      <LiveInspector
        jobId="job1"
        selectedFile="docs/architecture.md"
        parser="gemini-markdown"
        onClose={() => {}}
        injectedArtifact={mdArtifact}
      />
    );
    expect(screen.getByText("docs/architecture.md")).toBeInTheDocument();
    expect(screen.getByText("Title")).toBeInTheDocument();
    expect(screen.getAllByTestId("li-entity-chip")).toHaveLength(1);
    expect(screen.getByText(/Entities \(1\)/)).toBeInTheDocument();
  });

  it("renders python artifact: source code, modules tree, entity + edge chips", () => {
    render(
      <LiveInspector
        jobId="job1"
        selectedFile="code/main.py"
        parser="python-ast"
        onClose={() => {}}
        injectedArtifact={pyArtifact}
      />
    );
    expect(screen.getByText("code/main.py")).toBeInTheDocument();
    expect(screen.getByText(/def hello/)).toBeInTheDocument();
    expect(screen.getByText(/module: main/)).toBeInTheDocument();
    expect(screen.getAllByTestId("li-entity-chip")).toHaveLength(2);
    expect(screen.getAllByTestId("li-edge-chip")).toHaveLength(1);
  });

  it("renders pdf artifact: <embed type=application/pdf> + liteparse sections", () => {
    const { container } = render(
      <LiveInspector
        jobId="jobpdf"
        selectedFile="docs/whitepaper.pdf"
        parser="liteparse"
        onClose={() => {}}
        injectedArtifact={pdfArtifact}
      />
    );
    const embed = container.querySelector('embed[type="application/pdf"]') as HTMLEmbedElement | null;
    expect(embed).not.toBeNull();
    expect(embed?.getAttribute("src")).toContain(
      "/api/ingest/jobpdf/file/raw?path=docs%2Fwhitepaper.pdf"
    );
    // Liteparse pane: sections + image count summary
    expect(screen.getByText("Introduction")).toBeInTheDocument();
    expect(screen.getByText("Background")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument(); // image_count
    expect(screen.getAllByTestId("li-entity-chip")).toHaveLength(1);
  });

  it("renders sql artifact: tables tree with columns", () => {
    render(
      <LiveInspector
        jobId="job1"
        selectedFile="db/schema.sql"
        parser="sqlglot"
        onClose={() => {}}
        injectedArtifact={sqlArtifact}
      />
    );
    expect(screen.getByText("db/schema.sql")).toBeInTheDocument();
    expect(screen.getByText(/CREATE TABLE users/)).toBeInTheDocument();
    expect(screen.getAllByText("users").length).toBeGreaterThan(0);
    expect(screen.getByText("id")).toBeInTheDocument();
    expect(screen.getByText("name")).toBeInTheDocument();
  });
});
