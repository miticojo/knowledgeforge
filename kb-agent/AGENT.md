# 🤖 AGENT.md - Agentic KB Context & Rules

This document provides essential context and rigorous instructions for **any AI Coding Assistant or Agent** working on the `kb-agent` repository. 
Read this entirely before making modifications to the schema, logic, or infrastructure.

## 1. Project Overview & Architecture
* **Goal**: Build an "Agentic Enterprise Knowledge Base" using Gemini and Cloud Spanner to process unstructured IT/Business documents into a Queryable Knowledge Graph.
* **Paradigm**: Agentic workflow combined with **GraphRAG** (Graph Retrieval-Augmented Generation) and **Generative UI** via CopilotKit.
* **Stack**: Python (ADK Backend), Next.js 15 + React (AG-UI Frontend), Google Cloud SDK, Vertex AI (Gemini 2.5 Flash / Embeddings 004), Cloud Spanner (Graph Property DB), Terraform.
* **Security**: Google Cloud Model Armor as an active ADK Shield callback against prompt injections and data leaks.

## 2. The Ontology Standard: ArchiMate 3.2 (MANDATORY)
The entire Knowledge Graph and extraction prompts are strictly bound to the **The Open Group ArchiMate 3.2** structural standard. 
**NEVER** introduce custom, generic, or overlapping node types (e.g., do not use `App`, `Server`, `DB`, `Database`).

### 2.1 Allowed Entities (Wave 2)
All extraction and database modeling MUST use the exact following CamelCase definitions mapping to ArchiMate 3.2:

**Strategy Layer:**
*   `Capability` (Business capabilities, organizational abilities)

**Business Layer:**
*   `BusinessActor` (Teams, Organizations, People, Source Systems)
*   `BusinessRole` (Named responsibilities: Application Owner, Data Steward)
*   `BusinessProcess` (Operational workflows, procedures)
*   `BusinessFunction` (Competency groupings: Finance, HR, IT Operations)
*   `BusinessService` (Exposed business behavior: Customer Support, Billing Service)
*   `BusinessObject` (Business-level information concepts: Customer, Order, Invoice)
*   `Contract` (SLAs, formal agreements, NDAs)

**Application Layer:**
*   `ApplicationComponent` (Software, Microservices, Applications)
*   `ApplicationService` (Exposed application behavior: Payment API, Auth Service)
*   `ApplicationInterface` (Access points: REST API, GraphQL Endpoint)
*   `DataObject` (Structured data for automated processing: Customer Record, Invoice Data)

**Technology Layer:**
*   `Node` (Computational resources: Servers, VMs, Container hosts)
*   `Device` (Physical hardware: Routers, Firewalls, Load Balancers)
*   `SystemSoftware` (DBMS, OS, Middleware: Oracle, Linux, Docker)
*   `TechnologyService` (Infrastructure services: DNS, Storage, Messaging)
*   `Artifact` (Deployable files: JARs, configs, Docker images)
*   `CommunicationNetwork` (Networks: Corporate LAN, VPN, Internet)

**Motivation Layer:**
*   `Goal` (Strategic objectives: Reduce TCO, Improve SLA)
*   `Requirement` (Functional/non-functional requirements)
*   `Constraint` (Architectural limitations, specialization of Requirement)
*   `Stakeholder` (Roles with interests in the architecture: CTO, Enterprise Architect)

### 2.2 Allowed Relationships (Edges)
Spanner Edge Tables and Traversal queries must use ArchiMate 3.2 relationship types:

**Structural:**
*   `Composition` — part-of with existence dependency (e.g., Node -> Device)
*   `Aggregation` — part-of without existence dependency (e.g., BusinessFunction -> BusinessProcess)
*   `Assignment` — responsibility/execution allocation (e.g., BusinessActor -> BusinessProcess, Node -> Artifact)
*   `Realization` — implementation/concretization (e.g., ApplicationComponent -> Requirement)

**Dependency:**
*   `Serving` — provider -> consumer (e.g., ApplicationComponent -> BusinessProcess)
*   `Access` — behavior -> passive structure (e.g., ApplicationComponent -> DataObject)
*   `Influence` — impact on motivation (e.g., Goal -> Requirement)
*   `Association` — generic/unspecified relationship

**Dynamic:**
*   `Triggering` — temporal/causal precedence (e.g., ProcessA -> ProcessB)
*   `Flow` — transfer of information/goods (e.g., ProcessA -> ProcessB, label: "order data")

**Other:**
*   `Specialization` — is-a hierarchy (e.g., Constraint -> Requirement)

## 3. Core File System & Change Management

If you modify the schema or the ingestion logic, you **MUST** ensure consistency across the triad of Knowledge Graph files. The ontology now encompasses **22 entity types** and **11 relationship types**. If you change one, you usually must update the other two:

1.  **`ontology.yaml`**: The single source of truth for the extraction schema. 
2.  **`models/ontology.py`**: A python script that *dynamically* reads `ontology.yaml` and produces Pydantic `BaseModel` classes using `create_model()`. **RULE:** Do not hardcode Pydantic Entity classes here! The code strictly generates them at runtime.
3.  **`../database/spanner_schema.sdl`**: The Cloud Spanner Graph Property DDL. Must have a table for every Entity in the YAML and exact edge representations.

## 4. Agentic Workflows & FastAPI (`agents/`)
*   `coordinator.py`: The orchestrator router wrapped as an `ADKAgent`. Delegated to via CopilotKit and `ag_ui_adk`. Uses `SearchAgent` and `DocAgent` as `AgentTool` for A2A delegation. Instruction tells the LLM to rephrase chunk content cleanly (no raw copy-paste) and append a `<sources>` JSON block at the end of every response.
*   `processing.py`: (**High Priority**) Responsible for Document Ingestion. Uses Gemini 2.5 Flash with `FunctionCallingConfig(mode="ANY")` to force sequential tool execution (one tool per LLM turn). Pipeline: `extract_metadata` → `extract_embeddings` (gemini-embedding-001 via Vertex AI) → `search_existing_entities` → `extract_graph` (con post-processing ArchiMate forzato) → `write_to_spanner`.
*   `search.py`: The Retrieval Agent. Uses a **3-query HippoRAG pipeline**:
    - **Q1** (SQL): Hybrid `UNION ALL` of keyword (`LIKE`) + vector ANN (`COSINE_DISTANCE`) in one query.
    - **Q2** (GQL): Standalone `GRAPH KnowledgeGraph MATCH (src)-[rel]-(tgt)` with **bidirectional** traversal per entity type. GQL is ~1.3x faster than GRAPH_TABLE and supports bidirectional matching (incoming + outgoing edges).
    - **Q3** (SQL): HippoRAG graph→text bridge — from graph-discovered entity names, find additional chunks via `LIKE %entity%` in a single `OR` query.
    - Response includes a `<sources>` JSON block for the frontend `SourcesBox`.
*   `doc.py`: Generator of Markdown/Docs relying purely on the context provided by `search.py` via session state (`last_search_result`).
*   `security.py`: Integrates `google-cloud-modelarmor` using an ADK `before_agent_callback` to intercept unsafe prompts.

## 5. Frontend-Backend Integration (AG-UI Protocol)
*   The frontend does **NOT** use `useCopilotAction` with `available: "remote"` for backend tools. This pattern does not work because ADK backend tools are Python functions, not `AGUIToolset` client proxy tools.
*   Instead, the frontend uses a **fetch interceptor** that clones the SSE response from `/api/copilotkit` and parses `TOOL_CALL_START`, `TOOL_CALL_ARGS`, and `TOOL_CALL_RESULT` events to update the pipeline UI with progressive staggering.
*   The `CopilotChat` component is hidden but rendered to maintain hook functionality.
*   PDF parsing uses **LiteParse** with **PDFium** (`PdfiumRenderer.extractImageBounds()`) to detect embedded images per page. Only pages with images are screenshotted — not all pages. The `PdfiumRenderer` is imported via `file://` URL to bypass the package `exports` restriction.

## 6. Coding Principles for this Repo
*   **Do not mock LLM calls** in production code unless specifically asked to stub. Utilize `@google/genai` or the designated vertex AI SDK.
*   **Infrastructure as Code**: Any new required Google Cloud resource (e.g. Buckets, IAM roles) MUST run through `terraform/`. Do not assume manual console creation.
*   **Language**: Commit messages, Python comments, and technical Markdown can be in English or Italian as per context, but code variables and Schema names MUST be in English and adhere to ArchiMate naming conventions.

## 6.1 Optional Extras (setup.py)
The agent ships a `setup.py` that exposes optional integrations as **extras**
on top of `requirements.txt`:

```bash
pip install -e .          # core
pip install -e ".[kc]"    # adds google-cloud-dataplex for the Knowledge
                          # Catalog exporter (services/kc_exporter.py)
```

The exporter is **disabled by default** (`KC_SYNC_ENABLED=false`). See
`docs/concepts/knowledge-catalog-bridge.md` for the ArchiMate <-> KC mapping.

## 7. Multi-Tenancy & Race Condition Mitigations
*   **Thread Safety**: ADK's `ThreadPoolExecutor` does NOT propagate Python `contextvars`. Do not rely on thread-local or module-global variables to pass request-scoped context (like tenant ID or search scope) to background tools.
*   **Session State**: Use `ToolContext.state` to pass parameters to tools. The `TenantMiddleware` extracts headers into the agent state, which is then accessible in tools via `tool_context.state.get("headers")`.
*   **Header Normalization**: Always split header values by comma and take the first element (e.g., `header.split(",")[0].strip()`) to handle cases where proxies or CopilotKit duplicate header values (e.g., `"mine, mine"`).
