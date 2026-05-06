# ArchiSurance Extended Benchmark v2 — Design Specification

## Context

The current ArchiSurance evaluation dataset (17 PDFs, 196 entities, 208 relationships, 30 questions) tests only enterprise architecture documents. It lacks code artifacts, IaC, data pipelines, API specs, diagrams, long documents, and governance scenarios.

This spec extends ArchiSurance into a comprehensive benchmark covering all capabilities: KG extraction from heterogeneous sources, hybrid retrieval, answer quality, architecture conformance, data governance, impact analysis, entity resolution across formats, and long document handling.

## Design Decisions

- **Code realism**: mix of structural skeletons + 2-3 fully executable files
- **Data stack**: dbt + BigQuery for data pipeline governance
- **App stack**: Multi-stack (Java Spring Boot + Python FastAPI + TypeScript NestJS)
- **Target size**: ~60 artifacts total (17 existing + ~43 new)
- **API specs**: OpenAPI 3.0 YAML files for key services
- **Diagrams**: PlantUML component and sequence diagrams

---

## 1. Artifact Inventory (~60 total)

### 1.1 Existing PDF Documents (17)
No changes. Files `doc_01` through `doc_17` remain as-is.

### 1.2 New Long-Form PDF Documents (5)

| File | Pages | Size Target | Content |
|------|-------|-------------|---------|
| `doc_18_full_architecture_dossier.pdf` | 80 | ~300 KB | All 5 ArchiMate layers in a single document. Tests long-document chunking and retrieval. |
| `doc_19_annual_ea_report_2025.pdf` | 120 | ~500 KB | Annual EA report with metrics, trends, KPIs, decisions, roadmap. Tests extraction from very long documents with position bias. |
| `doc_20_microservice_design_guide.pdf` | 50 | ~200 KB | Design patterns, code examples inline, decision records. Tests extraction from mixed prose+code. |
| `doc_21_data_governance_handbook.pdf` | 50 | ~200 KB | Data policies, lineage rules, quality standards, data catalog entries, PII classification. Tests data governance extraction. |
| `doc_22_incident_postmortem_collection.pdf` | 30 | ~100 KB | 10 incidents (3 pages each): root cause, impact chain, remediation. Tests impact analysis ground truth. |

### 1.3 Code: Java Claims Service (5 files, Hexagonal Architecture)

```
code/java/claims-service/
  ClaimsController.java        — @RestController, REST endpoints (ApplicationInterface: Claims API)
  ClaimsService.java           — @Service, business logic (ApplicationComponent: Claims Management Platform)
  ClaimsRepository.java        — @Repository, JPA data access (Access → DataObject: Claim Record)
  ClaimsDomainModel.java       — @Entity, domain objects (BusinessObject: Claim, Customer Profile)
  pom.xml                      — Dependencies: spring-boot, postgresql, kafka-clients
```

**Intentional violations for conformance testing:**
- ClaimsController directly imports ClaimsRepository (layer bypass — controller→repository)
- Missing interface for ClaimsService (no port/adapter separation)

### 1.4 Code: Python Risk Engine (5 files, Clean Architecture)

```
code/python/risk-engine/
  api/risk_endpoints.py        — FastAPI routes (ApplicationInterface: Risk Scoring API)
  services/risk_calculator.py  — Core logic (ApplicationComponent: Risk Engine)
  models/risk_models.py        — Pydantic models (DataObject: Risk Score, Premium Calculation Data)
  adapters/kafka_producer.py   — Kafka integration (Flow → SystemSoftware: Apache Kafka)
  requirements.txt             — Dependencies: fastapi, sqlalchemy, confluent-kafka
```

**Clean implementation — no intentional violations.** Serves as positive conformance example.

### 1.5 Code: TypeScript Customer Portal (5 files, NestJS Layered)

```
code/typescript/customer-portal/
  customer.controller.ts       — NestJS @Controller (ApplicationInterface: Mobile App Interface)
  customer.service.ts          — @Injectable service (ApplicationComponent: Customer Self-Service Portal)
  customer.entity.ts           — TypeORM @Entity (DataObject: Customer Record)
  crm-client.service.ts        — HTTP client to CRM API (Serving: Portal → CRM System)
  package.json                 — Dependencies: @nestjs/core, typeorm, axios
```

**Intentional violation:** crm-client.service.ts calls CRM API using hardcoded URL (no config injection).

### 1.6 Infrastructure as Code: Terraform (8 files)

```
infra/terraform/
  main.tf              — Provider config (google, google-beta), backend (GCS)
  gke.tf               — GKE cluster (Node: App Server Cluster, SystemSoftware: Kubernetes)
  cloudsql.tf          — Cloud SQL instances (Node: Database Server Primary, SystemSoftware: PostgreSQL 15)
  networking.tf        — VPC, subnets, firewall rules (CommunicationNetwork: Corporate LAN, DMZ Network)
  iam.tf               — Service accounts, IAM bindings (BusinessRole → Assignment)
  monitoring.tf        — Monitoring stack (TechnologyService: Monitoring Service)
  variables.tf         — Input variables
  terraform.tfvars     — Values (with intentional issues)
```

**Intentional violations for governance testing:**
- `networking.tf`: firewall rule with `0.0.0.0/0` source range (too permissive)
- `iam.tf`: service account with `roles/owner` (overprivileged)
- `cloudsql.tf`: no `backup_configuration` block (missing backup)
- `gke.tf`: missing `labels` on cluster resource (untagged)
- `terraform.tfvars`: hardcoded IP address (should be variable)

### 1.7 Data Pipeline: dbt + BigQuery (5 files)

```
data/dbt/archisurance_analytics/
  models/staging/stg_claims.sql           — SELECT from source, basic transforms
  models/marts/fraud_scores.sql           — Joins stg_claims + external fraud data (DataObject: Fraud Score Dataset)
  models/marts/premium_analytics.sql      — Aggregations for premium calculation
  models/schema.yml                       — Tests, descriptions, column docs
  models/sources.yml                      — Source definitions with freshness
```

**Intentional violations for data governance testing:**
- `fraud_scores.sql`: references raw table directly (bypasses staging)
- `schema.yml`: `premium_analytics` model has no `description`
- `schema.yml`: `stg_claims` missing `not_null` test on primary key
- `sources.yml`: `raw_customers` source missing `loaded_at_field` (no freshness monitoring)

### 1.8 API Specifications: OpenAPI (3 files)

```
api/
  claims-api.yaml              — OpenAPI 3.0: Claims API endpoints, schemas, auth
  risk-scoring-api.yaml        — OpenAPI 3.0: Risk Scoring API with request/response schemas
  customer-api.yaml            — OpenAPI 3.0: Customer Portal API
```

Each spec references entities from the ArchiMate model (ApplicationInterface, DataObject schemas) and includes:
- Endpoint definitions matching code implementations
- Schema definitions matching domain models
- Security schemes (OAuth2, API key)
- **Intentional drift:** claims-api.yaml defines an endpoint `/v2/claims/bulk` not present in ClaimsController.java (API spec drift)

### 1.9 Architecture Diagrams: PlantUML (4 files)

```
diagrams/
  component-overview.puml      — High-level component diagram (all ApplicationComponents + Serving)
  claims-sequence.puml         — Sequence diagram: claims processing flow
  infrastructure-deployment.puml — Deployment diagram: nodes, containers, networks
  data-flow.puml               — Data flow diagram: DataObjects through processes
```

Each diagram embeds ArchiMate entities with stereotypes. The diagrams are the "intended architecture" — deviations in code/IaC are intentional violations.

**Intentional deviation:** `component-overview.puml` shows Risk Engine connected to PostgreSQL, but `cloudsql.tf` provisions only Oracle (architecture drift).

---

## 2. Test Categories (10 categories, 100 scenarios)

### Category 1: KG Extraction Quality (L1)
Tests entity and relationship extraction from heterogeneous artifacts.

| # | Scenario | Source | Expected |
|---|----------|--------|----------|
| 1.1 | Entity extraction from short PDF (3 pages) | doc_04 | ~20 entities, 15 relationships |
| 1.2 | Entity extraction from long PDF (80 pages) | doc_18 | ~80 entities, no loss vs sum of individual docs |
| 1.3 | Entity extraction from very long PDF (120 pages) | doc_19 | ~60 entities, handles position bias |
| 1.4 | Entity extraction from Java code | ClaimsService.java | ApplicationComponent, DataObject, ApplicationInterface |
| 1.5 | Entity extraction from Python code | risk_calculator.py | ApplicationComponent, DataObject |
| 1.6 | Entity extraction from TypeScript code | customer.service.ts | ApplicationComponent, Serving relationships |
| 1.7 | Entity extraction from Terraform | gke.tf, cloudsql.tf | Node, SystemSoftware, CommunicationNetwork |
| 1.8 | Entity extraction from dbt schema.yml | schema.yml | DataObject, Access relationships, data contracts |
| 1.9 | Entity extraction from OpenAPI spec | claims-api.yaml | ApplicationInterface, DataObject schemas |
| 1.10 | Entity extraction from PlantUML diagram | component-overview.puml | All components + Serving relationships |
| 1.11 | Noise resilience in code (comments, TODO, dead code) | All code files | No entities from noise |
| 1.12 | Cross-format entity count consistency | All artifacts | Total unique entities matches ground truth |

### Category 2: Retrieval Quality (L2)
Tests hybrid retrieval across heterogeneous sources.

| # | Scenario | Query | Source types involved |
|---|----------|-------|---------------------|
| 2.1 | Single-hop from document | "Which DB does Claims Platform use?" | PDF |
| 2.2 | Single-hop from code | "What dependencies does ClaimsService import?" | Java |
| 2.3 | Single-hop from Terraform | "What GKE version is configured?" | .tf |
| 2.4 | Multi-hop cross-format | "If GKE cluster version changes, which business processes are affected?" | .tf → PDF |
| 2.5 | Data lineage query | "Where does fraud_scores model get its source data?" | dbt .sql + .yml |
| 2.6 | Long document retrieval (info at page 95) | "What was decided about Oracle migration timeline?" | doc_19 (120 pages) |
| 2.7 | Code + doc cross-reference | "Does ClaimsService code match the architecture in doc_05?" | .java + PDF |
| 2.8 | API spec + code alignment | "Does claims-api.yaml match the actual ClaimsController endpoints?" | .yaml + .java |
| 2.9 | Diagram + code alignment | "Does the component diagram match the actual service topology?" | .puml + code |
| 2.10 | Negative test: unanswerable | "What is the CEO's email address?" | None (should refuse) |

### Category 3: Answer Quality (L3)
Tests answer faithfulness, relevancy, and correctness.

| # | Scenario | Type |
|---|----------|------|
| 3.1 | Answer from single document | Baseline faithfulness |
| 3.2 | Answer synthesizing 3+ documents | Cross-doc synthesis |
| 3.3 | Answer integrating doc + code | Multi-format coherence |
| 3.4 | Answer with numbers/metrics (SLA, RPO, RTO) | Factual precision |
| 3.5 | Answer with dates and timeline | Temporal accuracy |
| 3.6 | "I don't know" answer (info not present) | Refusal quality |
| 3.7 | Ambiguous question (2 interpretations) | Disambiguation |
| 3.8 | Long answer (list all components of a layer) | Completeness |
| 3.9 | Reasoning answer (impact analysis) | Reasoning quality |
| 3.10 | Answer requiring code understanding | Code comprehension |

### Category 4: Architecture Conformance
Tests rule violation detection.

| # | Scenario | Rule | Expected |
|---|----------|------|----------|
| 4.1 | Layer violation: SystemSoftware→BusinessProcess | ARCH-002 | Detected in graph |
| 4.2 | Orphan entity (zero connections) | QUAL-001 | Detected |
| 4.3 | Missing Serving on ApplicationComponent | ARCH-001 | Detected |
| 4.4 | Circular dependency in Java code | NEW: CODE-001 | ClaimsController→ClaimsRepository→ClaimsService→ClaimsController |
| 4.5 | Layer bypass: Controller→Repository | NEW: CODE-002 | Java Hexagonal violation |
| 4.6 | Terraform: resource without labels | NEW: IAC-001 | gke.tf cluster missing labels |
| 4.7 | Terraform: overpermissive firewall | NEW: IAC-002 | 0.0.0.0/0 in networking.tf |
| 4.8 | dbt: model without tests | NEW: DBT-001 | premium_analytics in schema.yml |
| 4.9 | dbt: source without freshness | NEW: DBT-002 | raw_customers in sources.yml |
| 4.10 | API spec drift: endpoint in spec but not in code | NEW: API-001 | /v2/claims/bulk missing from ClaimsController |
| 4.11 | Diagram drift: component in diagram but wrong connection in code | NEW: DIAG-001 | Risk Engine→PostgreSQL in diagram, Oracle in Terraform |

### Category 5: Data Governance
Tests data governance rule validation.

| # | Scenario | Rule | Expected |
|---|----------|------|----------|
| 5.1 | High fan-in DataObject without contract | DG-001 | Detected |
| 5.2 | PII data without encryption reference | NEW: DG-002 | Customer Record in doc without encryption |
| 5.3 | dbt model without description | NEW: DG-003 | premium_analytics |
| 5.4 | dbt source without loaded_at_field | NEW: DG-004 | raw_customers |
| 5.5 | Data lineage gap: created but not consumed | NEW: DG-005 | DataObject without outgoing Access |
| 5.6 | Data lineage gap: consumed but source unknown | NEW: DG-006 | No incoming Flow |
| 5.7 | PII on public cloud (constraint violation) | NEW: DG-007 | doc_16 + Terraform |
| 5.8 | Schema change impact not tracked | NEW: DG-008 | dbt + app code |
| 5.9 | dbt: missing not_null test on PK column | NEW: DG-009 | stg_claims.claim_id |
| 5.10 | DataObject without retention policy | NEW: DG-010 | Audit Log without TTL |

### Category 6: Impact Analysis
Tests blast radius calculation correctness.

| # | Scenario | Source entity | Expected blast radius |
|---|----------|--------------|----------------------|
| 6.1 | Decommission Kubernetes | SystemSoftware | 12+ AppComponents, 20+ processes |
| 6.2 | PostgreSQL failure | SystemSoftware | Claims Platform, PAS, CRM → processes |
| 6.3 | Corporate LAN outage | CommunicationNetwork | All nodes → all apps |
| 6.4 | Customer Record breach | DataObject | Apps accessing → processes → stakeholders |
| 6.5 | GKE cluster deletion (from Terraform) | Node | Cluster → pods → apps → processes |
| 6.6 | fraud_scores dbt model failure | DataObject | Downstream models → apps → processes |
| 6.7 | Oracle 19c vendor discontinuation | SystemSoftware | Billing, Data Warehouse → processes, goals |
| 6.8 | Payment API deprecation | ApplicationService | Billing System → payment processes |
| 6.9 | Confidence-filtered impact (EXTRACTED only) | Any | Smaller but more reliable radius |
| 6.10 | Multi-hop limit test (1 vs 2 vs 4 hops) | Apache Kafka | Progressive radius growth |

### Category 7: Entity Resolution
Tests cross-format entity reconciliation.

| # | Scenario | Formats |
|---|----------|---------|
| 7.1 | Alias in text: "CRM System" vs "Salesforce CRM" | PDF vs PDF |
| 7.2 | Terraform resource name vs domain name | .tf vs PDF |
| 7.3 | Java package vs component name | .java vs PDF |
| 7.4 | dbt model name vs DataObject name | .sql vs PDF |
| 7.5 | Terraform resource vs Node name | .tf vs PDF |
| 7.6 | Abbreviation: "PAS" vs "Policy Administration System" | Cross-doc |
| 7.7 | Version variants: "PostgreSQL 15" vs "postgres:15-alpine" | PDF vs Docker |
| 7.8 | TypeScript import path vs component name | .ts vs PDF |
| 7.9 | OpenAPI operationId vs code function name | .yaml vs .java |
| 7.10 | False positive: "system" (generic) vs "CRM System" (specific) | Noise |

### Category 8: Long Document Handling
Tests performance across document sizes.

| # | Scenario | Size | Metric |
|---|----------|------|--------|
| 8.1 | 3-page micro-document | ~2 KB | Extraction completeness |
| 8.2 | 15-page standard document | ~40 KB | Baseline |
| 8.3 | 50-page departmental dossier | ~150 KB | Chunking quality |
| 8.4 | 80-page full architecture dossier | ~300 KB | Long-doc retrieval |
| 8.5 | 120-page annual EA report | ~500 KB | Stress test |
| 8.6 | Info at page 3 vs page 95 (position bias) | Long doc | No position bias |
| 8.7 | Large table (50 rows) in long document | Long doc | Table extraction |
| 8.8 | Referenced but missing diagram | Doc with "[See Figure 3]" | No hallucination |
| 8.9 | Document with internal duplicates | Repetitive doc | Deduplication |
| 8.10 | Multi-version: v1.0 and v2.1 of same topic | 2 docs | Temporal reasoning |

### Category 9: Code Architecture Extraction
Tests extraction from source code.

| # | Scenario | Language | Expected extraction |
|---|----------|---------|-------------------|
| 9.1 | Spring annotations → components | Java | ApplicationComponent from @Service, @Controller |
| 9.2 | Maven/Gradle dependencies → graph | Java | SystemSoftware dependencies |
| 9.3 | Interface + implementation → Realization | Java | Realization relationships |
| 9.4 | FastAPI routes → interfaces | Python | ApplicationInterface from @app.get |
| 9.5 | SQLAlchemy models → DataObjects | Python | DataObject extraction |
| 9.6 | NestJS modules → components | TypeScript | ApplicationComponent from @Module |
| 9.7 | HTTP client calls → Serving | TypeScript | Inter-service relationships |
| 9.8 | Dockerfile → SystemSoftware | Docker | Runtime dependencies |
| 9.9 | docker-compose → topology | Docker Compose | Service topology |
| 9.10 | OpenAPI schemas → DataObject | YAML | Data model extraction |

### Category 10: IaC & Data Pipeline Governance
Tests infrastructure and data pipeline rules.

| # | Scenario | File | Rule |
|---|----------|------|------|
| 10.1 | Terraform: missing labels | gke.tf | IAC-001 |
| 10.2 | Terraform: no backup config | cloudsql.tf | IAC-003 |
| 10.3 | Terraform: no network policy on GKE | gke.tf | IAC-004 |
| 10.4 | Terraform: roles/owner on SA | iam.tf | IAC-005 |
| 10.5 | Terraform: hardcoded values | terraform.tfvars | IAC-006 |
| 10.6 | dbt: model without PK test | schema.yml | DBT-001 |
| 10.7 | dbt: staging accesses raw directly | stg_claims.sql | DBT-003 |
| 10.8 | dbt: no materialization specified | fraud_scores.sql | DBT-004 |
| 10.9 | dbt: source without column definitions | sources.yml | DBT-005 |
| 10.10 | Cross: Terraform DB ≠ dbt source | .tf + .yml | CROSS-001 |

---

## 3. Extended Architecture Rules (YAML)

New rules to add to `config/architecture_rules.yaml`:

```yaml
# --- Code Architecture Rules ---
- id: "CODE-001"
  description: "No circular dependencies between code modules"
  category: "code"
  severity: "error"
  type: "no_circular"

- id: "CODE-002"
  description: "Controllers must not directly access repositories (layer bypass)"
  category: "code"
  severity: "error"
  type: "forbidden_edge"
  source_type: "ApplicationInterface"
  target_type: "DataObject"
  relationship_type: "Access"

# --- IaC Rules ---
- id: "IAC-001"
  description: "All Terraform resources must have environment and team labels"
  category: "iac"
  severity: "warning"
  type: "required_metadata"
  artifact_type: "terraform"
  required_labels: ["environment", "team"]

- id: "IAC-002"
  description: "No firewall rules allowing 0.0.0.0/0 ingress"
  category: "iac"
  severity: "error"
  type: "forbidden_pattern"
  artifact_type: "terraform"
  pattern: "0.0.0.0/0"

# --- dbt Rules ---
- id: "DBT-001"
  description: "Every dbt model must have at least one test defined"
  category: "data_pipeline"
  severity: "warning"
  type: "dbt_model_test"

- id: "DBT-002"
  description: "Every dbt source must have freshness monitoring"
  category: "data_pipeline"
  severity: "warning"
  type: "dbt_source_freshness"

# --- Data Governance Rules ---
- id: "DG-002"
  description: "DataObjects containing PII must reference encryption controls"
  category: "data_governance"
  severity: "error"
  type: "pii_encryption"

- id: "DG-003"
  description: "Every dbt model must have a description"
  category: "data_governance"
  severity: "warning"
  type: "dbt_model_description"

# --- API Rules ---
- id: "API-001"
  description: "Every OpenAPI endpoint should have a corresponding implementation"
  category: "api"
  severity: "warning"
  type: "spec_implementation_alignment"

# --- Diagram Rules ---
- id: "DIAG-001"
  description: "Architecture diagrams should match actual deployed infrastructure"
  category: "diagram"
  severity: "warning"
  type: "diagram_infrastructure_alignment"
```

---

## 4. Extended Ground Truth

### New entities (~60 from new artifacts)

**From code (15):**
- ApplicationInterface: Claims API (from Java), Risk Scoring API (from Python), Mobile App API (from TS)
- ApplicationComponent: claims-service module, risk-engine module, customer-portal module
- DataObject: ClaimRecord (from JPA @Entity), RiskScore (from Pydantic), CustomerRecord (from TypeORM)
- SystemSoftware: spring-boot, fastapi, nestjs, kafka-clients (from dependency files)

**From Terraform (15):**
- Node: gke-archisurance-cluster, cloudsql-primary, cloudsql-replica
- SystemSoftware: kubernetes (from GKE), postgresql (from Cloud SQL)
- CommunicationNetwork: vpc-main, subnet-private, subnet-public, firewall-allow-internal
- TechnologyService: cloud-monitoring, cloud-logging

**From dbt (10):**
- DataObject: stg_claims, fraud_scores, premium_analytics (models as data products)
- DataObject: raw_claims, raw_customers, raw_fraud_external (sources)
- Flow: raw_claims → stg_claims → fraud_scores (lineage)

**From OpenAPI (10):**
- ApplicationInterface: POST /claims, GET /claims/{id}, POST /risk/score, etc.
- DataObject: ClaimRequest, ClaimResponse, RiskScoreResult (from schemas)

**From diagrams (10):**
- All entities referenced in PlantUML with stereotypes

### New eval questions (~70, total ~100)

Distribution across new categories:
- Category 4 (Conformance): 11 questions with known violations
- Category 5 (Data Governance): 10 questions with known issues
- Category 6 (Impact Analysis): 10 questions with expected blast radius
- Category 7 (Entity Resolution): 10 cross-format questions
- Category 8 (Long Document): 10 size-scaling questions
- Category 9 (Code Extraction): 10 code-specific questions
- Category 10 (IaC/dbt Governance): 10 infrastructure questions

---

## 5. Generator Architecture

Extend `generate_test_docs.py` into a modular generator:

```
evaluation/data/archisurance/
  generate_test_docs.py          — Existing PDF generator (unchanged)
  generate_code_artifacts.py     — NEW: generates Java/Python/TS skeletons
  generate_iac_artifacts.py      — NEW: generates Terraform files
  generate_dbt_artifacts.py      — NEW: generates dbt project
  generate_api_specs.py          — NEW: generates OpenAPI YAML
  generate_diagrams.py           — NEW: generates PlantUML files
  generate_long_docs.py          — NEW: generates 50-120 page PDFs
  generate_all.py                — NEW: orchestrator that runs all generators
  generate_ground_truth_v2.py    — NEW: generates extended ground truth + eval questions
```

Each generator:
1. Reads the shared entity/relationship model
2. Generates artifacts with embedded ground truth
3. Injects intentional violations where specified
4. Outputs to appropriate subdirectory under `evaluation/data/archisurance/`

---

## 6. Verification Plan

### Automated
- `python generate_all.py` — generates all artifacts
- `python run_eval.py` — runs all 3 existing layers (L1, L2, L3) on extended dataset
- New: `python run_eval.py --layer L4` — conformance evaluation
- New: `python run_eval.py --layer L5` — data governance evaluation
- New: `python run_eval.py --layer L6` — impact analysis evaluation

### Manual spot-checks
- Verify intentional violations are detected by conformance checker
- Verify impact analysis blast radius matches expected values
- Verify entity resolution across code/IaC/dbt/docs
- Verify long document retrieval has no position bias

### Success criteria
- L1 Entity Micro-F1 >= 0.85 on extended dataset
- L2 Pipeline Recall >= 0.60 on new question categories
- Conformance: all intentional violations detected (100% true positive rate)
- Impact Analysis: blast radius within 20% of expected values
- Entity Resolution: >= 80% cross-format entity reconciliation
