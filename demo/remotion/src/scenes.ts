// Walkthrough scenes — each entry pairs a captured screenshot with a title +
// narration block. Durations are in seconds; total = sum of all + 1s opening.
export interface Scene {
  image: string;
  title: string;
  body: string;
  duration: number; // seconds
}

export const SCENES: Scene[] = [
  {
    image: "scenes/01_welcome.png",
    title: "KnowledgeForge",
    body: "Agentic GraphRAG over ArchiMate. Documents and code become one navigable knowledge graph.",
    duration: 5,
  },
  {
    image: "scenes/02_architecture.png",
    title: "Architecture",
    body: "Five-layer stack: ingestion -> graph store on Spanner -> hybrid retrieval -> ADK coordinator -> CopilotKit UI.",
    duration: 6,
  },
  {
    image: "scenes/03_ingestion_empty.png",
    title: "Ingestion - two sources",
    body: "Upload tab for PDFs / Markdown via LiteParse. Code Repository tab for Git via tree-sitter AST + Gemini controlled-generation.",
    duration: 6,
  },
  {
    image: "scenes/04_doc_chosen.png",
    title: "Pick a document",
    body: "We choose a small markdown describing the ArchiSurance claim intake process.",
    duration: 4,
  },
  {
    image: "scenes/05_doc_running.png",
    title: "Live Agent Timeline",
    body: "Right column streams real backend events: route -> parse -> map to ArchiMate -> write. Counters update as the agent works.",
    duration: 6,
  },
  {
    image: "scenes/06_doc_kg.png",
    title: "Knowledge Graph - extracted",
    body: "Customer, ClaimHandler, ClaimsAPI, FraudScorer, PostgresDB. Colored by ArchiMate layer, edges typed by relationship.",
    duration: 6,
  },
  {
    image: "scenes/07_doc_inspector.png",
    title: "Live Inspector",
    body: "Click any file to see source on the left and parsed entities on the right. Source-aware: markdown renders, code shows AST.",
    duration: 6,
  },
  {
    image: "scenes/08_git_form.png",
    title: "Code Repository ingest",
    body: "Point at any Git URL. Globs include .py / .md / .sql. Each file routes to the right parser based on extension.",
    duration: 5,
  },
  {
    image: "scenes/09_git_timeline.png",
    title: "Per-file routing",
    body: "Python files use tree-sitter AST. Markdown goes through Gemini structured extraction. SQL via sqlglot. All in parallel, all streamed.",
    duration: 6,
  },
  {
    image: "scenes/10_git_python.png",
    title: "Python source + AST",
    body: "Source numbered on the left. Right pane shows the extracted modules, classes, functions and their imports.",
    duration: 6,
  },
  {
    image: "scenes/11_git_markdown.png",
    title: "Markdown to ArchiMate",
    body: "Architecture markdown is parsed by Gemini into typed ArchiMate entities and relationships, ready to merge into the graph.",
    duration: 6,
  },
  {
    image: "scenes/12_git_delta.png",
    title: "Delta graph",
    body: "Mini canvas shows just the entities and edges added by THIS run, color-coded by layer. Click through to the full graph.",
    duration: 5,
  },
  {
    image: "scenes/13_graph.png",
    title: "Graph explorer",
    body: "Filter by ArchiMate layer or entity type, search, scope to a sub-graph. Cmd-click to expand a neighborhood.",
    duration: 6,
  },
  {
    image: "scenes/14_embeddings_default.png",
    title: "Embedding space",
    body: "Every entity is embedded with Gemini-Embedding-2 (768d). PCA projects to 3D so we can see semantic clusters.",
    duration: 5,
  },
  {
    image: "scenes/15_embeddings_query.png",
    title: "Project a query",
    body: "Type any query: it gets embedded with the same model, projected into the same PCA basis, and the cosine top-30 hits light up.",
    duration: 6,
  },
  {
    image: "scenes/16_chat_answer.png",
    title: "Agentic chat",
    body: "Hybrid retrieval (keyword + vector + graph traversal) feeds the Coordinator agent. Answer cites the source documents and code that prove it.",
    duration: 8,
  },
  {
    image: "scenes/17_dashboard.png",
    title: "Cost + telemetry",
    body: "Per-tenant Spanner / LLM cost broken down by operation, with a daily trend. Out-of-band side-channel keeps UI numbers honest.",
    duration: 6,
  },
];

export const FPS = 30;
export const WIDTH = 1600;
export const HEIGHT = 1000;
