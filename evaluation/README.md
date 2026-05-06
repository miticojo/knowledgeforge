# KB Evaluation Framework

End-to-end evaluation of the Knowledge Base pipeline across multiple layers, using the ArchiSurance v2 benchmark dataset.

## Architecture

```
L1: KG Construction Quality     L2: Retrieval Quality          L3: Answer Quality
(entity/relation F1)            (graph vs vector A/B)          (faithfulness/relevancy)
       |                               |                              |
  kg_quality.py                 retrieval_quality.py            answer_quality.py
       |                               |                              |
       +---------- run_eval.py (orchestrator) -------------------------+
                          |
                    data/ground_truth/
```

## Setup

```bash
cd evaluation
pip install -r requirements.txt
```

## Usage

```bash
# Full evaluation (requires running backend + Spanner with ingested data)
python run_eval.py

# Individual layers
python run_eval.py --layer L1   # KG construction quality
python run_eval.py --layer L2   # Retrieval comparison (graph vs vector)
python run_eval.py --layer L3   # Answer quality (LLM-as-judge)

# Generate test data
python run_eval.py --generate-data          # Generate original 17 PDFs
cd data/archisurance && python generate_long_docs.py  # Generate 5 long-form PDFs (48-118 pages)
```

## ArchiSurance v2 Benchmark Dataset

### Artifact Inventory (57 artifacts)

| Category | Count | Format | Purpose |
|----------|-------|--------|---------|
| **Architecture PDFs** (original) | 17 | PDF (15-40 pages) | Enterprise architecture documents with embedded entities and aliases |
| **Long-form PDFs** (new) | 5 | PDF (12-118 pages) | Long document chunking, position bias, multi-section synthesis |
| **Java Claims Service** | 5 | .java, .xml | Hexagonal Architecture extraction, layer violation detection |
| **Python Risk Engine** | 5 | .py, .txt | Clean Architecture extraction (positive reference) |
| **TypeScript Customer Portal** | 5 | .ts, .json | NestJS layered extraction, cross-service calls |
| **Terraform IaC** | 8 | .tf, .tfvars | Infrastructure extraction, governance rule validation |
| **dbt Data Pipeline** | 5 | .sql, .yml | Data lineage, data governance rules |
| **OpenAPI Specs** | 3 | .yaml | API contract extraction, spec-code drift detection |
| **PlantUML Diagrams** | 4 | .puml | Architecture diagram extraction, diagram-code drift |

### Directory Structure

```
data/archisurance/
  doc_01..doc_17*.pdf              # Original 17 architecture PDFs
  doc_18..doc_22*.pdf              # 5 new long-form PDFs
  generate_test_docs.py            # Original PDF generator
  generate_long_docs.py            # Long-form PDF generator
  code/
    java/claims-service/           # 5 Java files (Spring Boot, Hexagonal)
    python/risk-engine/            # 5 Python files (FastAPI, Clean Architecture)
    typescript/customer-portal/    # 5 TypeScript files (NestJS, Layered)
  infra/terraform/                 # 8 Terraform files (GCP: GKE, Cloud SQL, VPC, IAM)
  data/dbt/archisurance_analytics/ # 5 dbt files (staging, marts, sources, schema)
  api/                             # 3 OpenAPI 3.0 specs
  diagrams/                        # 4 PlantUML architecture diagrams

data/ground_truth/
  archisurance_ground_truth.json   # Original: 196 entities, 208 relationships
  extended_ground_truth.json       # v2: +55 entities, +45 relationships, 16 violations
  eval_questions.json              # Original: 30 questions (6 categories)
  eval_questions_v2.json           # v2: 30 new questions (8 new categories)
  entity_aliases.json              # Cross-document name aliases
```

### Intentional Violations (16 total)

Embedded in artifacts for conformance and governance testing:

| Source | Violations | Examples |
|--------|-----------|----------|
| **Java code** | 3 | Controller→Repository bypass, direct repo access |
| **Terraform** | 6 | Missing labels, 0.0.0.0/0 firewall, no backup, roles/owner, hardcoded IP |
| **dbt** | 6 | Direct table ref (bypassing source()), missing description, missing PK test, no freshness |
| **OpenAPI** | 1 | /claims/bulk endpoint in spec but not in code (API drift) |

### Evaluation Questions (60 total)

| Category | Count | Source | Tests |
|----------|-------|--------|-------|
| **single_hop** | 8 | Original | Direct relationship lookups |
| **multi_hop** | 8 | Original | 2-3 step graph traversals |
| **cross_document** | 6 | Original | Multi-PDF synthesis |
| **entity_resolution** | 4 | Original | Alias deduplication |
| **completeness** | 2 | Original | Exhaustive entity enumeration |
| **graph_advantage** | 2 | Original | Deep traversal (4-5 hops) |
| **code_extraction** | 5 | v2 | Entity extraction from Java/Python/TS |
| **iac_extraction** | 3 | v2 | Entity extraction from Terraform |
| **data_lineage** | 2 | v2 | dbt lineage traversal |
| **conformance** | 5 | v2 | Architecture violation detection |
| **data_governance** | 5 | v2 | Data governance rule validation |
| **impact_analysis** | 3 | v2 | Blast radius calculation |
| **entity_resolution_cross_format** | 3 | v2 | Cross-format entity reconciliation |
| **cross_format_consistency** | 2 | v2 | Doc vs code vs IaC alignment |
| **long_document** | 2 | v2 | Retrieval from 80-120 page docs |

## Metrics

### L1: KG Construction Quality
- **Entity Type F1**: Precision/recall per ArchiMate type vs ground truth
- **Relationship F1**: Relationship type coverage and distribution
- **Ontology Conformance**: Valid entities/relations per ArchiMate 3.2
- **Entity Resolution Accuracy**: Dedup correctness across documents and formats
- **Confidence Distribution**: EXTRACTED/INFERRED/AMBIGUOUS breakdown

### L2: Retrieval Quality (Graph vs Vector A/B)
- **Context Recall@K**: Expected entities found in retrieved chunks
- **Multi-hop Recall**: Graph traversal answers for 2+ hop questions
- **Graph Uplift**: Delta between full pipeline and vector-only
- **Cross-format Retrieval**: Retrieval from code, IaC, dbt sources

### L3: Answer Quality (LLM-as-Judge)
- **Faithfulness**: Grounded in retrieved context (no hallucination)
- **Relevancy**: Addresses the question asked
- **Correctness**: Matches expected ground truth answer

### L4: Architecture Conformance (via /graph/conformance)
- **Rule Pass Rate**: % of architecture rules satisfied
- **Violation Detection**: Intentional violations correctly identified
- **Layer Violation Detection**: Cross-layer forbidden edges found
- **Orphan Detection**: Entities with zero connections flagged

### L5: Data Governance (via conformance rules)
- **Data Contract Coverage**: DataObjects with documentation
- **Freshness Monitoring**: dbt sources with loaded_at_field
- **PK Test Coverage**: dbt models with primary key tests
- **Lineage Completeness**: Data flow gaps detected

### L6: Impact Analysis (via /graph/impact)
- **Blast Radius Accuracy**: Impacted entities vs expected
- **Confidence Decay**: EXTRACTED-only radius vs full radius
- **Layer Coverage**: Impact propagation across ArchiMate layers

## Latest Results (2026-04-12)

| Metric | Value |
|--------|-------|
| L2 Pipeline Recall | 0.628 |
| L2 Vector-Only Recall | 0.699 |
| L2 Graph Uplift | -0.071 (needs gate tuning) |
| L2 Multi-hop Uplift | +0.002 (positive) |
| Conformance | 3/10 passed, 5 warnings, 1 error |
| Edge Confidence | 97% EXTRACTED, 3% INFERRED |
