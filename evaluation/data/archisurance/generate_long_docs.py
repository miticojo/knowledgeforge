"""Generate long-form PDF documents (50-120 pages) for ArchiSurance v2 benchmark.

Creates 5 PDFs of varying length to test:
- Long document chunking and retrieval
- Position bias (info at page 3 vs page 95)
- Table extraction in large documents
- Multi-section synthesis
- Document deduplication

Reuses the DocPDF class and entity model from generate_test_docs.py.
"""
import os
import sys
import random

random.seed(42)

# Import from the existing generator
sys.path.insert(0, os.path.dirname(__file__))
from generate_test_docs import DocPDF, ENTITIES, RELATIONSHIPS, ENTITY_ALIASES, _use, _track

OUT_DIR = os.path.dirname(__file__)

# Extended filler prose for padding long documents
LONG_FILLER = [
    "The enterprise architecture practice at ArchiSurance has evolved significantly over the past decade, transitioning from a documentation-centric approach to an active governance model that integrates continuous feedback loops with development teams.",
    "Quarterly architecture reviews have become a cornerstone of the governance process, bringing together stakeholders from business, technology, and operations to assess alignment between strategic objectives and technical implementation.",
    "The adoption of cloud-native technologies has fundamentally changed how the organization thinks about infrastructure provisioning, moving from months-long procurement cycles to self-service platforms that enable teams to deploy in minutes.",
    "Technical debt management remains a persistent challenge, with legacy systems accounting for approximately 35% of the total IT budget. The architecture team has implemented a systematic approach to identifying, quantifying, and prioritizing technical debt reduction.",
    "Cross-functional alignment between the claims processing domain and the underwriting domain has improved through shared data models and event-driven integration patterns, reducing manual handoffs by an estimated 60%.",
    "The data governance framework establishes clear ownership, quality standards, and lifecycle policies for all enterprise data assets, ensuring compliance with GDPR, PCI-DSS, and industry-specific regulations.",
    "Performance benchmarking has revealed that the current claims processing pipeline handles peak loads of 15,000 claims per hour, with 99th percentile latency under 2 seconds for API responses.",
    "The microservices migration strategy follows a strangler fig pattern, gradually replacing monolithic components with independently deployable services while maintaining backward compatibility.",
    "Capacity planning models project a 40% increase in transaction volumes over the next 18 months, driven by the expansion into the commercial insurance market and the launch of digital self-service channels.",
    "The security architecture review identified 23 findings across the application portfolio, of which 5 were rated critical and have been remediated through the quarterly patch cycle.",
    "Observability improvements have reduced mean time to detection (MTTD) from 45 minutes to under 5 minutes, primarily through the introduction of distributed tracing and anomaly detection on key business metrics.",
    "The integration architecture team has standardized on event-driven patterns using Apache Kafka for asynchronous communication and REST APIs with OpenAPI specifications for synchronous request-response interactions.",
    "Cost optimization initiatives in the cloud infrastructure have yielded a 22% reduction in monthly compute costs through right-sizing, committed use discounts, and automated scaling policies.",
    "The disaster recovery strategy has been validated through quarterly DR drills, with the last exercise achieving a recovery time of 47 minutes against the target RTO of 60 minutes.",
    "Developer experience improvements include the introduction of a self-service platform engineering portal, standardized CI/CD pipelines, and automated architecture conformance checks in the build process.",
    "The data warehouse modernization project migrated 12 TB of historical data from on-premise Oracle to BigQuery, enabling real-time analytics dashboards for claims processing and fraud detection.",
    "API management has been centralized through the API Gateway, which now handles over 2 million requests per day with an average response time of 120 milliseconds.",
    "The container orchestration platform (Kubernetes) runs 150 pods across 3 node pools, with horizontal pod autoscaling configured for all production workloads.",
    "Network segmentation has been implemented following a zero-trust model, with micro-segmentation between service tiers and mandatory mutual TLS for all inter-service communication.",
    "The regulatory compliance dashboard provides real-time visibility into the status of 47 compliance controls across GDPR, PCI-DSS, SOX, and Solvency II requirements.",
]


def _gen_doc18():
    """Full Architecture Dossier - 80 pages, all layers."""
    doc_id = "doc_18"
    pdf = DocPDF("Full Architecture Dossier", "EA-DOSSIER-001",
                 "Enterprise Architecture Team")
    pdf.title_page("Comprehensive Architecture Overview - All Layers", "3.0")
    pdf.version_history()

    toc = [
        ("1", "Executive Summary"),
        ("2", "Strategic Architecture"),
        ("3", "Business Architecture"),
        ("4", "Application Architecture"),
        ("5", "Technology Architecture"),
        ("6", "Data Architecture"),
        ("7", "Security Architecture"),
        ("8", "Integration Architecture"),
        ("9", "Migration Roadmap"),
        ("10", "Governance & Compliance"),
        ("11", "Appendices"),
    ]
    pdf.toc(toc)

    # Section 1: Executive Summary
    pdf.add_page()
    pdf.h1("1. Executive Summary")
    pdf.para(
        f"This dossier provides a comprehensive view of the ArchiSurance enterprise architecture "
        f"across all five ArchiMate layers. The architecture supports {len(ENTITIES.get('Capability', []))} "
        f"strategic capabilities, {len(ENTITIES.get('ApplicationComponent', []))} application components, "
        f"and {len(ENTITIES.get('SystemSoftware', []))} technology platforms."
    )
    for filler in LONG_FILLER[:3]:
        pdf.para(filler)

    # Section 2: Strategic Architecture
    pdf.add_page()
    pdf.h1("2. Strategic Architecture")
    pdf.para("The strategic layer defines the capabilities that ArchiSurance must develop to achieve its vision.")
    for cap in ENTITIES.get("Capability", []):
        pdf.h3(f"2.x. {_use(doc_id, cap)}")
        pdf.para(f"The {_use(doc_id, cap)} capability is essential for achieving the strategic goals "
                 f"of ArchiSurance. It is realized through specific business processes and supported "
                 f"by dedicated application components.")
        pdf.para(random.choice(LONG_FILLER))

    # Section 3: Business Architecture
    pdf.add_page()
    pdf.h1("3. Business Architecture")
    pdf.h2("3.1 Business Actors and Roles")
    for actor in ENTITIES.get("BusinessActor", []):
        pdf.bullet(f"{_use(doc_id, actor)} - responsible for key business functions")
    pdf.h2("3.2 Business Processes")
    for proc in ENTITIES.get("BusinessProcess", []):
        pdf.h3(f"Process: {_use(doc_id, proc)}")
        pdf.para(f"The {_use(doc_id, proc)} process is a critical business operation that "
                 f"supports the operational objectives of ArchiSurance.")
        pdf.para(random.choice(LONG_FILLER))

    # Section 4: Application Architecture
    pdf.add_page()
    pdf.h1("4. Application Architecture")
    pdf.h2("4.1 Application Portfolio")
    for app in ENTITIES.get("ApplicationComponent", []):
        pdf.h3(f"Component: {_use(doc_id, app)}")
        pdf.para(f"The {_use(doc_id, app)} is a key application component deployed on "
                 f"{_use(doc_id, 'Kubernetes')} within the {_use(doc_id, 'App Server Cluster')}.")
        pdf.para(random.choice(LONG_FILLER))

    pdf.h2("4.2 Application Services and Interfaces")
    for svc in ENTITIES.get("ApplicationService", []):
        pdf.bullet(f"{_use(doc_id, svc)} - exposed via {_use(doc_id, 'API Gateway')}")

    # Section 5: Technology Architecture
    pdf.add_page()
    pdf.h1("5. Technology Architecture")
    pdf.h2("5.1 Infrastructure Nodes")
    for node in ENTITIES.get("Node", []):
        pdf.bullet(f"{_use(doc_id, node)}")
    pdf.h2("5.2 System Software")
    for sw in ENTITIES.get("SystemSoftware", []):
        pdf.h3(f"Platform: {_use(doc_id, sw)}")
        pdf.para(f"{_use(doc_id, sw)} is a critical technology platform supporting "
                 f"multiple application components in the ArchiSurance landscape.")
        pdf.para(random.choice(LONG_FILLER))

    # Section 6-8: More content to reach 80 pages
    for section_num, section_title in [("6", "Data Architecture"), ("7", "Security Architecture"),
                                        ("8", "Integration Architecture")]:
        pdf.add_page()
        pdf.h1(f"{section_num}. {section_title}")
        for i in range(6):
            pdf.h2(f"{section_num}.{i+1} {section_title} - Detail Area {i+1}")
            pdf.para(random.choice(LONG_FILLER))
            pdf.para(random.choice(LONG_FILLER))
            # Embed some entities
            entities_pool = list(ENTITIES.get("DataObject", [])) + list(ENTITIES.get("Goal", []))
            if entities_pool:
                ent = random.choice(entities_pool)
                pdf.para(f"The {_use(doc_id, ent)} is managed according to enterprise standards.")

    # Section 9: Migration Roadmap (embeds goals and constraints)
    pdf.add_page()
    pdf.h1("9. Migration Roadmap")
    for goal in ENTITIES.get("Goal", []):
        pdf.h3(f"Goal: {_use(doc_id, goal)}")
        pdf.para(f"Achievement of {_use(doc_id, goal)} requires coordinated effort across "
                 f"multiple departments and technology platforms.")
        pdf.para(random.choice(LONG_FILLER))
    for constraint in ENTITIES.get("Constraint", []):
        pdf.bullet(f"Constraint: {_use(doc_id, constraint)}")

    # Section 10: Governance
    pdf.add_page()
    pdf.h1("10. Governance & Compliance")
    for req in ENTITIES.get("Requirement", [])[:5]:
        pdf.bullet(f"Requirement: {_use(doc_id, req)}")
    for filler in LONG_FILLER[10:16]:
        pdf.para(filler)

    # Appendices (noise)
    pdf.add_page()
    pdf.h1("11. Appendices")
    pdf.noise_meeting_notes()
    pdf.noise_disclaimer()

    # Pad to ~80 pages
    while pdf.page_no() < 78:
        pdf.para(random.choice(LONG_FILLER))

    path = os.path.join(OUT_DIR, "doc_18_full_architecture_dossier.pdf")
    pdf.output(path)
    print(f"  Generated {path} ({pdf.page_no()} pages)")


def _gen_doc19():
    """Annual EA Report 2025 - 120 pages."""
    doc_id = "doc_19"
    pdf = DocPDF("Annual Enterprise Architecture Report 2025", "EA-ANNUAL-2025")
    pdf.title_page("Architecture Achievements, Metrics, and Strategic Direction", "1.0")
    pdf.version_history()

    toc_items = [(str(i), f"Chapter {i}") for i in range(1, 13)]
    pdf.toc(toc_items)

    chapters = [
        "Executive Summary and Key Achievements",
        "Architecture Maturity Assessment",
        "Application Portfolio Analysis",
        "Technology Landscape Review",
        "Cloud Migration Progress",
        "Security Posture Report",
        "Data Architecture Evolution",
        "Integration Platform Status",
        "Performance and Reliability Metrics",
        "Strategic Goals Progress",
        "Budget and Cost Analysis",
        "Recommendations and Next Steps",
    ]

    for ch_num, ch_title in enumerate(chapters, 1):
        pdf.add_page()
        pdf.h1(f"{ch_num}. {ch_title}")

        # Each chapter has 3-4 subsections with embedded entities
        for sub in range(4):
            pdf.h2(f"{ch_num}.{sub+1} Analysis Area {sub+1}")

            # Embed entities contextually
            all_entities = []
            for etype in ENTITIES:
                all_entities.extend(ENTITIES[etype])
            for _ in range(3):
                ent = random.choice(all_entities)
                pdf.para(f"Analysis of {_use(doc_id, ent)} shows continued improvement in "
                         f"alignment with enterprise standards and strategic objectives.")
                pdf.para(random.choice(LONG_FILLER))

            # Add some metrics tables
            if sub == 0 and ch_num <= 6:
                pdf.table(
                    ["Metric", "Target", "Actual", "Status"],
                    [
                        ["System Availability", "99.9%", "99.87%", "At Risk"],
                        ["API Response Time (p95)", "<500ms", "320ms", "On Track"],
                        ["Deployment Frequency", ">10/week", "14/week", "Exceeded"],
                        ["Change Failure Rate", "<5%", "3.2%", "On Track"],
                        ["MTTR", "<60min", "47min", "On Track"],
                    ]
                )

        # Filler to reach target length
        for _ in range(3):
            pdf.para(random.choice(LONG_FILLER))

    # Goal progress (important info buried deep in the document - tests position bias)
    pdf.add_page()
    pdf.h1("10. Strategic Goals Progress")
    pdf.para("The following table summarizes progress against the eight strategic goals "
             "defined in the ArchiSurance IT Strategy 2024-2027.")
    for goal in ENTITIES.get("Goal", []):
        pdf.h3(f"Goal: {_use(doc_id, goal)}")
        pdf.para(f"Progress on {_use(doc_id, goal)}: The initiative is tracking at 72% completion "
                 f"with key milestones achieved in Q1 and Q2 2025. Remaining work focuses on "
                 f"integration testing and stakeholder sign-off.")
        for stakeholder in random.sample(ENTITIES.get("Stakeholder", []), min(2, len(ENTITIES.get("Stakeholder", [])))):
            pdf.bullet(f"Champion: {_use(doc_id, stakeholder)}")

    # Pad to ~120 pages
    while pdf.page_no() < 118:
        pdf.para(random.choice(LONG_FILLER))

    pdf.noise_disclaimer()

    path = os.path.join(OUT_DIR, "doc_19_annual_ea_report_2025.pdf")
    pdf.output(path)
    print(f"  Generated {path} ({pdf.page_no()} pages)")


def _gen_doc20():
    """Microservice Design Guide - 50 pages with inline code examples."""
    doc_id = "doc_20"
    pdf = DocPDF("Microservice Design Guide", "EA-DESIGN-001")
    pdf.title_page("Architecture Patterns, Code Standards, and Best Practices", "2.0")
    pdf.version_history()

    pdf.add_page()
    pdf.h1("1. Architecture Patterns")
    pdf.para(f"All microservices at ArchiSurance follow the Hexagonal Architecture pattern. "
             f"The {_use(doc_id, 'Claims Management Platform')} and {_use(doc_id, 'Risk Engine')} "
             f"are the reference implementations.")

    pdf.h2("1.1 Hexagonal Architecture")
    pdf.para("The hexagonal pattern separates domain logic from infrastructure concerns:")
    pdf.code_block("""
@Service
public class ClaimsService {
    private final ClaimsPersistencePort port;
    // Domain logic here - no framework dependencies
}""")

    pdf.h2("1.2 Event-Driven Integration")
    pdf.para(f"Services communicate asynchronously via {_use(doc_id, 'Apache Kafka')} topics. "
             f"The {_use(doc_id, 'Enterprise Service Bus')} handles message routing and transformation.")
    pdf.code_block("""
# Risk Engine publishes to Kafka
await kafka.publish("risk.scores", {
    "claim_id": claim_id,
    "score": 0.75
})""")

    # API design standards
    pdf.add_page()
    pdf.h1("2. API Design Standards")
    pdf.para(f"All APIs must be documented using OpenAPI 3.0 and registered with the "
             f"{_use(doc_id, 'API Gateway')}.")
    for svc in ENTITIES.get("ApplicationService", [])[:5]:
        pdf.bullet(f"{_use(doc_id, svc)} - REST endpoint with JWT authentication")

    # Data access patterns
    pdf.add_page()
    pdf.h1("3. Data Access Patterns")
    pdf.para(f"Primary data store: {_use(doc_id, 'PostgreSQL 15')} for transactional data, "
             f"{_use(doc_id, 'Redis')} for caching, {_use(doc_id, 'Elasticsearch')} for search.")
    for data_obj in ENTITIES.get("DataObject", []):
        pdf.bullet(f"Data object: {_use(doc_id, data_obj)}")

    # Deployment standards
    pdf.add_page()
    pdf.h1("4. Deployment Standards")
    pdf.para(f"All services deploy to {_use(doc_id, 'Kubernetes')} on the "
             f"{_use(doc_id, 'App Server Cluster')}. Container images are built via CI/CD "
             f"and stored in Artifact Registry.")
    pdf.code_block("""
# Dockerfile standard
FROM eclipse-temurin:21-jre-alpine
COPY target/claims-service.jar /app/
ENTRYPOINT ["java", "-jar", "/app/claims-service.jar"]""")

    # Pad to ~50 pages
    while pdf.page_no() < 48:
        pdf.para(random.choice(LONG_FILLER))

    path = os.path.join(OUT_DIR, "doc_20_microservice_design_guide.pdf")
    pdf.output(path)
    print(f"  Generated {path} ({pdf.page_no()} pages)")


def _gen_doc21():
    """Data Governance Handbook - 50 pages."""
    doc_id = "doc_21"
    pdf = DocPDF("Data Governance Handbook", "DG-HANDBOOK-001")
    pdf.title_page("Data Quality, Lineage, Privacy, and Lifecycle Policies", "2.0")
    pdf.version_history()

    pdf.add_page()
    pdf.h1("1. Data Governance Framework")
    pdf.para("ArchiSurance's data governance framework establishes policies for data quality, "
             "lineage tracking, privacy compliance, and lifecycle management across all data assets.")

    pdf.h2("1.1 Data Ownership")
    pdf.para(f"Each data object must have a designated data owner. The {_use(doc_id, 'Data Analytics Team')} "
             f"serves as the central governance body.")
    for data_obj in ENTITIES.get("DataObject", []):
        pdf.bullet(f"{_use(doc_id, data_obj)} - Owner: {_use(doc_id, random.choice(ENTITIES.get('BusinessActor', [])))}")

    pdf.h2("1.2 Data Quality Standards")
    pdf.para("All data objects must meet minimum quality thresholds:")
    pdf.table(
        ["Data Object", "Completeness", "Accuracy", "Timeliness"],
        [[_use(doc_id, do), ">95%", ">98%", "<24h"] for do in ENTITIES.get("DataObject", [])[:5]]
    )

    # Data lineage
    pdf.add_page()
    pdf.h1("2. Data Lineage")
    pdf.para(f"Data flows through the ArchiSurance landscape from source systems "
             f"({_use(doc_id, 'CRM System')}, {_use(doc_id, 'Claims Management Platform')}) "
             f"through staging layers to analytical marts in the {_use(doc_id, 'Data Warehouse')}.")
    pdf.para(f"The data pipeline uses dbt (data build tool) on BigQuery for transformation, "
             f"with source freshness monitoring and automated quality tests.")

    # Privacy and compliance
    pdf.add_page()
    pdf.h1("3. Privacy and Compliance")
    pdf.para(f"PII data (Customer Profile, Customer Record) must be encrypted at rest and in transit. "
             f"The {_use(doc_id, 'GDPR Compliance')} requirement mandates right-to-erasure capability.")
    for req in ENTITIES.get("Requirement", []):
        if any(kw in req for kw in ["GDPR", "PCI", "SOX"]):
            pdf.bullet(f"Compliance requirement: {_use(doc_id, req)}")

    # Data retention
    pdf.add_page()
    pdf.h1("4. Data Retention Policies")
    pdf.para("Each data object has a defined retention period based on regulatory and business requirements.")
    pdf.table(
        ["Data Object", "Retention Period", "Regulation", "Archival"],
        [
            [_use(doc_id, "Insurance Policy"), "10 years", "Solvency II", "Cold storage"],
            [_use(doc_id, "Claim"), "7 years", "SOX", "Compressed archive"],
            [_use(doc_id, "Customer Profile"), "Until erasure request", "GDPR", "Anonymized"],
            [_use(doc_id, "Audit Log"), "5 years", "SOX", "Immutable storage"],
        ]
    )

    # Pad to ~50 pages
    while pdf.page_no() < 48:
        pdf.para(random.choice(LONG_FILLER))

    path = os.path.join(OUT_DIR, "doc_21_data_governance_handbook.pdf")
    pdf.output(path)
    print(f"  Generated {path} ({pdf.page_no()} pages)")


def _gen_doc22():
    """Incident Postmortem Collection - 30 pages (10 incidents x 3 pages)."""
    doc_id = "doc_22"
    pdf = DocPDF("Incident Postmortem Collection 2025", "OPS-POSTMORTEM-2025")
    pdf.title_page("Root Cause Analysis, Impact Assessment, and Remediation Actions", "1.0")
    pdf.version_history()

    incidents = [
        ("INC-2025-001", "Kubernetes Cluster Node Exhaustion",
         f"The {_use(doc_id, 'Kubernetes')} cluster on {_use(doc_id, 'App Server Cluster')} "
         f"ran out of resources due to memory leak in {_use(doc_id, 'Claims Management Platform')}.",
         f"All services on the cluster were affected: {_use(doc_id, 'Risk Engine')}, "
         f"{_use(doc_id, 'Fraud Detection Engine')}, {_use(doc_id, 'Customer Self-Service Portal')}.",
         "Memory limit enforcement + HPA tuning"),
        ("INC-2025-002", "PostgreSQL Replication Lag",
         f"{_use(doc_id, 'PostgreSQL 15')} replication lag on {_use(doc_id, 'Database Server Replica')} "
         f"exceeded 30 seconds during peak claims processing.",
         f"Read queries from {_use(doc_id, 'Policy Administration System')} returned stale data.",
         "Increased replication slots + connection pooling"),
        ("INC-2025-003", "Apache Kafka Partition Rebalance",
         f"{_use(doc_id, 'Apache Kafka')} triggered unexpected partition rebalance, "
         f"causing 5-minute message processing delay.",
         f"The {_use(doc_id, 'Enterprise Service Bus')} stopped receiving events, "
         f"affecting {_use(doc_id, 'Billing System')} and {_use(doc_id, 'Notification Service')}.",
         "Static partition assignment + consumer group tuning"),
        ("INC-2025-004", "API Gateway Certificate Expiry",
         f"TLS certificate on {_use(doc_id, 'API Gateway')} expired, blocking all external traffic.",
         f"Customer-facing services ({_use(doc_id, 'Customer Self-Service Portal')}, "
         f"{_use(doc_id, 'Broker Portal')}) were inaccessible for 23 minutes.",
         "Automated cert renewal via cert-manager"),
        ("INC-2025-005", "Fraud Detection Model Drift",
         f"The {_use(doc_id, 'Fraud Detection Engine')} ML model (fraud-scoring-model.onnx) "
         f"showed 40% increase in false positives after data distribution shift.",
         f"{_use(doc_id, 'Claims Assessment')} process backed up with manual reviews.",
         "Model retraining pipeline + data drift monitoring"),
        ("INC-2025-006", "Oracle Database Connection Pool Exhaustion",
         f"{_use(doc_id, 'Oracle Database 19c')} max connections reached, "
         f"blocking {_use(doc_id, 'Billing System')} and {_use(doc_id, 'Data Warehouse')} queries.",
         f"Invoice generation ({_use(doc_id, 'Broker Commission Settlement')}) delayed by 4 hours.",
         "Connection pool increase + query optimization"),
        ("INC-2025-007", "DMZ Firewall Rule Misconfiguration",
         f"A change to {_use(doc_id, 'DMZ Network')} firewall rules accidentally blocked "
         f"traffic from {_use(doc_id, 'Load Balancer F5')} to the application subnet.",
         f"All external traffic was blocked. Full outage for 12 minutes.",
         "Change review process + automated firewall testing"),
        ("INC-2025-008", "Redis Cache Eviction Storm",
         f"{_use(doc_id, 'Redis')} evicted cached sessions due to memory pressure, "
         f"causing {_use(doc_id, 'Customer Self-Service Portal')} users to be logged out.",
         f"~2000 active sessions lost. Customer complaints increased 300%.",
         "Redis maxmemory-policy tuned + session persistence added"),
        ("INC-2025-009", "Elasticsearch Index Corruption",
         f"{_use(doc_id, 'Elasticsearch')} primary shard became unassigned on "
         f"{_use(doc_id, 'Monitoring Server')}, losing 3 hours of log data.",
         f"Audit trail gap for compliance ({_use(doc_id, 'SOX Audit Trail')}).",
         "Snapshot schedule + replica count increase"),
        ("INC-2025-010", "Cloud VPN Tunnel Flapping",
         f"The {_use(doc_id, 'Cloud VPN')} tunnel to on-premise data center experienced "
         f"intermittent connectivity, affecting {_use(doc_id, 'Oracle Database 19c')} access.",
         f"The {_use(doc_id, 'ERP migration')} batch job failed after 6 retries.",
         "Dedicated interconnect provisioned"),
    ]

    for inc_id, title, root_cause, impact, remediation in incidents:
        pdf.add_page()
        pdf.h2(f"Postmortem: {inc_id} - {title}")
        pdf.h3("Root Cause")
        pdf.para(root_cause)
        pdf.h3("Impact")
        pdf.para(impact)
        pdf.h3("Remediation")
        pdf.para(remediation)
        pdf.h3("Lessons Learned")
        pdf.para(random.choice(LONG_FILLER))
        pdf.para(random.choice(LONG_FILLER))

    path = os.path.join(OUT_DIR, "doc_22_incident_postmortem_collection.pdf")
    pdf.output(path)
    print(f"  Generated {path} ({pdf.page_no()} pages)")


def main():
    print("=" * 60)
    print("GENERATING LONG-FORM DOCUMENTS (ArchiSurance v2)")
    print("=" * 60)

    _gen_doc18()
    _gen_doc19()
    _gen_doc20()
    _gen_doc21()
    _gen_doc22()

    print("\nDone! 5 long-form PDFs generated.")


if __name__ == "__main__":
    main()
