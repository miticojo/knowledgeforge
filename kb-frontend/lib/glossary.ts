/**
 * Glossary of technical terms used across KnowledgeForge.
 *
 * Each entry is keyed by a canonical short name (uppercase or PascalCase) that
 * matches the `term` prop passed to <GlossaryTooltip />. Lookups are
 * case-insensitive at the component layer.
 */

export interface GlossaryEntry {
  term: string;
  definition: string;
  link?: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  RRF: {
    term: "RRF — Reciprocal Rank Fusion",
    definition:
      "Reciprocal Rank Fusion (Cormack, 2009). Combines results from multiple retrievers by inverse rank position. KnowledgeForge uses weighted RRF: vector 1.0, keyword 0.4, graph 0.3.",
    link: "https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf",
  },
  GraphRAG: {
    term: "GraphRAG",
    definition:
      "Retrieval that traverses a knowledge graph in addition to vector similarity. Captures structural relationships between entities that are invisible to chunk-level retrieval.",
    link: "https://microsoft.github.io/graphrag/",
  },
  AgenticRAG: {
    term: "AgenticRAG",
    definition:
      "Retrieval pattern where an LLM agent decides how and when to retrieve. The agent can call tools, verify intermediate results, and loop until it has enough evidence to answer.",
  },
  ArchiMate: {
    term: "ArchiMate 3.2",
    definition:
      "Open Group enterprise architecture modeling standard. KnowledgeForge uses 22 entity types across 5 layers plus 11 relationship types to model extracted knowledge.",
    link: "https://pubs.opengroup.org/architecture/archimate3-doc/",
  },
  EXTRACTED: {
    term: "EXTRACTED",
    definition:
      "Confidence label applied to an edge that was directly extracted from source text with high confidence. One of three labels: EXTRACTED, INFERRED, AMBIGUOUS.",
  },
  INFERRED: {
    term: "INFERRED",
    definition:
      "Confidence label applied to an edge that was derived by reasoning over other facts rather than stated explicitly in the source. One of three labels: EXTRACTED, INFERRED, AMBIGUOUS.",
  },
  AMBIGUOUS: {
    term: "AMBIGUOUS",
    definition:
      "Confidence label applied to an edge whose source text supports multiple interpretations. Flagged for review. One of three labels: EXTRACTED, INFERRED, AMBIGUOUS.",
  },
  HippoRAG: {
    term: "HippoRAG",
    definition:
      "NeurIPS 2024 paper. Uses Personalized PageRank over a knowledge graph for retrieval, inspired by the hippocampus's role in human memory indexing.",
    link: "https://arxiv.org/abs/2405.14831",
  },
  iText2KG: {
    term: "iText2KG",
    definition:
      "2024 paper introducing incremental text-to-knowledge-graph construction with entity reconciliation via cosine similarity thresholds.",
    link: "https://arxiv.org/abs/2409.03284",
  },
  CosineDistance: {
    term: "Cosine distance",
    definition:
      "Defined as 1 - cosine_similarity. KnowledgeForge uses < 0.15 as the entity merge threshold and < 0.45 as the vector retrieval cutoff.",
  },
  Coordinator: {
    term: "Coordinator",
    definition:
      "KnowledgeForge's main LLM agent (Gemini 2.5 Flash on Google ADK). Plans the retrieval, calls tools, and synthesizes the final answer.",
  },
  ADK: {
    term: "ADK — Agent Development Kit",
    definition:
      "Google's Agent Development Kit. The Python framework that KnowledgeForge's Coordinator agent runs on.",
    link: "https://google.github.io/adk-docs/",
  },
  "AG-UI": {
    term: "AG-UI — Agent User Interface",
    definition:
      "Open SSE streaming protocol for agent → frontend communication. KnowledgeForge uses it to stream tool calls, partial reasoning, and tokens to the browser.",
    link: "https://docs.ag-ui.com/",
  },
  MCP: {
    term: "MCP — Model Context Protocol",
    definition:
      "Anthropic's open standard for exposing tools and resources to LLM agents over a uniform JSON-RPC interface.",
    link: "https://modelcontextprotocol.io/",
  },
  KnowledgeCatalog: {
    term: "Knowledge Catalog (KC)",
    definition:
      "Google Cloud Dataplex's metadata service. KnowledgeForge integrates via an opt-in toolbox/exporter/importer to enrich and round-trip enterprise metadata.",
    link: "https://cloud.google.com/dataplex/docs/catalog-overview",
  },
};

/** Case-insensitive lookup. Returns undefined if no entry matches. */
export function lookupGlossary(term: string): GlossaryEntry | undefined {
  if (GLOSSARY[term]) return GLOSSARY[term];
  const normalized = term.toLowerCase();
  for (const key of Object.keys(GLOSSARY)) {
    if (key.toLowerCase() === normalized) return GLOSSARY[key];
  }
  return undefined;
}
