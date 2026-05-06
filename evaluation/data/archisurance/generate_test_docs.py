"""Generate comprehensive test PDF documents from a synthetic ArchiMate model.

Creates 17 PDF documents (15-40 pages each) with overlapping entities to test:
- Single-document extraction
- Cross-document entity resolution (entity aliases)
- Multi-hop graph traversal
- Noise filtering (meeting notes, disclaimers, version history, glossaries)
- Table extraction (decision records, SLA matrices, server inventories)
- Code snippet handling (config files, SQL, API specs)

The model simulates ArchiSurance, a mid-size insurance company, with ~160 entities
and ~220 relationships across all five ArchiMate layers.
"""

import json
import os
import random
import textwrap
from datetime import datetime
from fpdf import FPDF

# ---------------------------------------------------------------------------
# Seed for reproducibility
# ---------------------------------------------------------------------------
random.seed(42)

# ---------------------------------------------------------------------------
# Synthetic ArchiMate Model  (~160 entities across all layers)
# ---------------------------------------------------------------------------

ENTITIES = {
    # ── Strategy Layer ──
    "Capability": [
        "Digital Customer Experience",
        "Claims Processing Automation",
        "Risk Assessment Intelligence",
        "Omnichannel Distribution",
        "Data-Driven Underwriting",
        "Regulatory Compliance Management",
        "Operational Resilience",
        "Cyber Risk Mitigation",
        "Product Innovation",
        "Partner Ecosystem Integration",
    ],
    # ── Business Layer ──
    "BusinessActor": [
        "ArchiSurance HQ",
        "Claims Department",
        "Underwriting Team",
        "Customer",
        "Sales Division",
        "Finance Department",
        "IT Operations",
        "Legal & Compliance",
        "Broker Network",
        "Reinsurance Partner",
        "Call Center",
        "Product Development Unit",
        "Internal Audit",
        "Data Analytics Team",
        "HR Department",
        "Board of Directors",
    ],
    "BusinessRole": [
        "Claims Handler",
        "Policy Administrator",
        "Risk Analyst",
        "Customer Service Representative",
        "Underwriter",
        "Compliance Officer",
        "IT Service Manager",
        "Data Steward",
        "Security Officer",
        "Business Analyst",
        "Release Manager",
    ],
    "BusinessProcess": [
        "Customer Onboarding",
        "Policy Issuance",
        "Claims Registration",
        "Claims Assessment",
        "Premium Calculation",
        "Risk Evaluation",
        "Policy Renewal",
        "Fraud Detection",
        "Complaint Handling",
        "Regulatory Reporting",
        "Broker Commission Settlement",
        "Reinsurance Ceding",
        "Customer Identity Verification",
        "Document Digitization",
        "SLA Monitoring",
    ],
    "BusinessService": [
        "Insurance Policy Service",
        "Claims Handling Service",
        "Customer Portal Service",
        "Underwriting Service",
        "Premium Collection Service",
        "Fraud Investigation Service",
        "Regulatory Filing Service",
        "Broker Portal Service",
    ],
    "BusinessObject": [
        "Insurance Policy",
        "Claim",
        "Customer Profile",
        "Risk Score",
        "Invoice",
        "Commission Statement",
        "Regulatory Report",
        "Complaint Ticket",
        "Fraud Alert",
        "Reinsurance Treaty",
    ],
    "Contract": [
        "SLA Premium Support",
        "Reinsurance Agreement",
        "Broker Distribution Agreement",
        "Cloud Hosting SLA",
        "Third-Party Data Provider Contract",
    ],
    # ── Application Layer ──
    "ApplicationComponent": [
        "CRM System",
        "Policy Administration System",
        "Claims Management Platform",
        "Risk Engine",
        "Customer Self-Service Portal",
        "Document Management System",
        "Notification Service",
        "Fraud Detection Engine",
        "Reporting & Analytics Platform",
        "Enterprise Service Bus",
        "Identity & Access Management",
        "Billing System",
        "Broker Portal",
        "Data Warehouse",
        "Workflow Engine",
        "API Gateway",
        "Content Delivery Network",
        "Email Service",
        "Mobile App Backend",
        "Batch Processing Engine",
    ],
    "ApplicationService": [
        "Policy API",
        "Claims API",
        "Risk Scoring API",
        "Customer API",
        "Notification API",
        "Document API",
        "Fraud Scoring API",
        "Payment API",
        "Reporting API",
        "Authentication API",
    ],
    "ApplicationInterface": [
        "REST API Gateway",
        "Mobile App Interface",
        "Partner Integration Hub",
        "SOAP Legacy Interface",
        "GraphQL Analytics Endpoint",
    ],
    "DataObject": [
        "Policy Record",
        "Claim Record",
        "Customer Record",
        "Premium Calculation Data",
        "Fraud Score Dataset",
        "Commission Ledger",
        "Audit Log",
        "Regulatory Submission Record",
        "Document Metadata",
        "Analytics Cube",
    ],
    # ── Technology Layer ──
    "Node": [
        "App Server Cluster",
        "Database Server Primary",
        "Database Server Replica",
        "Batch Processing Node",
        "CI/CD Build Server",
        "Monitoring Server",
        "Log Aggregation Node",
        "DR Recovery Node",
        "Edge Cache Node",
        "GPU Analytics Node",
    ],
    "Device": [
        "Load Balancer F5",
        "Firewall Palo Alto",
        "SAN Storage Array",
        "Backup Tape Library",
        "HSM Appliance",
        "WAN Accelerator",
        "Network Switch Cisco Nexus",
        "Wireless Access Controller",
    ],
    "SystemSoftware": [
        "PostgreSQL 15",
        "Red Hat Linux 9",
        "Docker Engine",
        "Kubernetes",
        "Apache Kafka",
        "Elasticsearch",
        "Redis",
        "Nginx",
        "Oracle Database 19c",
        "Microsoft SQL Server 2022",
    ],
    "TechnologyService": [
        "Database Service",
        "Container Orchestration",
        "Message Queue Service",
        "Object Storage Service",
        "DNS Service",
        "Certificate Management Service",
        "Log Aggregation Service",
        "Secrets Management Service",
    ],
    "Artifact": [
        "claims-service.jar",
        "policy-api-v2.war",
        "risk-model-weights.pkl",
        "fraud-scoring-model.onnx",
        "notification-worker.jar",
        "etl-pipeline-config.yaml",
        "api-gateway-routes.json",
    ],
    "CommunicationNetwork": [
        "Corporate LAN",
        "DMZ Network",
        "Cloud VPN",
        "Management VLAN",
    ],
    # ── Motivation Layer ──
    "Goal": [
        "Reduce Claims Processing Time by 40%",
        "Achieve 99.9% System Availability",
        "Increase Customer Satisfaction to NPS 60+",
        "Automate 80% of Underwriting Decisions",
        "Zero Data Breaches by 2026",
        "Reduce IT Operational Costs by 25%",
        "Achieve Full Regulatory Compliance",
        "Migrate 100% Workloads to Cloud by 2027",
    ],
    "Requirement": [
        "Real-time Risk Scoring",
        "GDPR Compliance",
        "Multi-channel Access",
        "PCI-DSS Level 1 Certification",
        "SOX Audit Trail",
        "Sub-second API Response Time",
        "RPO of 15 minutes",
        "RTO of 1 hour",
        "Data Encryption at Rest and in Transit",
        "Role-based Access Control",
    ],
    "Constraint": [
        "Legacy Oracle DB Migration Deadline Q4 2026",
        "Budget Cap EUR 2M Annual",
        "No Public Cloud for PII Data (until 2026 review)",
        "Minimum 3 Availability Zones",
        "Vendor Lock-in Avoidance",
    ],
    "Stakeholder": [
        "CTO",
        "Head of Claims",
        "Chief Risk Officer",
        "Enterprise Architect",
        "CISO",
        "CFO",
    ],
}

# ---------------------------------------------------------------------------
# Relationships (~220)
# ---------------------------------------------------------------------------

RELATIONSHIPS = [
    # ── Business -> Business ──
    ("BusinessActor:Claims Department", "Assignment", "BusinessProcess:Claims Registration"),
    ("BusinessActor:Claims Department", "Assignment", "BusinessProcess:Claims Assessment"),
    ("BusinessActor:Claims Department", "Assignment", "BusinessProcess:Fraud Detection"),
    ("BusinessActor:Underwriting Team", "Assignment", "BusinessProcess:Risk Evaluation"),
    ("BusinessActor:Underwriting Team", "Assignment", "BusinessProcess:Premium Calculation"),
    ("BusinessActor:Sales Division", "Assignment", "BusinessProcess:Customer Onboarding"),
    ("BusinessActor:Sales Division", "Assignment", "BusinessProcess:Broker Commission Settlement"),
    ("BusinessActor:Finance Department", "Assignment", "BusinessProcess:Broker Commission Settlement"),
    ("BusinessActor:Legal & Compliance", "Assignment", "BusinessProcess:Regulatory Reporting"),
    ("BusinessActor:IT Operations", "Assignment", "BusinessProcess:SLA Monitoring"),
    ("BusinessActor:Call Center", "Assignment", "BusinessProcess:Complaint Handling"),
    ("BusinessActor:Call Center", "Assignment", "BusinessProcess:Customer Onboarding"),
    ("BusinessActor:Broker Network", "Assignment", "BusinessProcess:Customer Onboarding"),
    ("BusinessActor:Reinsurance Partner", "Assignment", "BusinessProcess:Reinsurance Ceding"),
    ("BusinessActor:Data Analytics Team", "Assignment", "BusinessProcess:Fraud Detection"),
    ("BusinessActor:Internal Audit", "Assignment", "BusinessProcess:Regulatory Reporting"),
    ("BusinessProcess:Customer Onboarding", "Triggering", "BusinessProcess:Policy Issuance"),
    ("BusinessProcess:Customer Onboarding", "Triggering", "BusinessProcess:Customer Identity Verification"),
    ("BusinessProcess:Claims Registration", "Triggering", "BusinessProcess:Claims Assessment"),
    ("BusinessProcess:Claims Assessment", "Flow", "BusinessProcess:Premium Calculation"),
    ("BusinessProcess:Claims Assessment", "Triggering", "BusinessProcess:Fraud Detection"),
    ("BusinessProcess:Policy Issuance", "Triggering", "BusinessProcess:Premium Calculation"),
    ("BusinessProcess:Policy Issuance", "Triggering", "BusinessProcess:Document Digitization"),
    ("BusinessProcess:Complaint Handling", "Triggering", "BusinessProcess:SLA Monitoring"),
    ("BusinessProcess:Regulatory Reporting", "Flow", "BusinessProcess:SLA Monitoring"),
    ("BusinessService:Insurance Policy Service", "Serving", "BusinessProcess:Policy Issuance"),
    ("BusinessService:Insurance Policy Service", "Serving", "BusinessProcess:Policy Renewal"),
    ("BusinessService:Claims Handling Service", "Serving", "BusinessProcess:Claims Registration"),
    ("BusinessService:Claims Handling Service", "Serving", "BusinessProcess:Claims Assessment"),
    ("BusinessService:Customer Portal Service", "Serving", "BusinessProcess:Complaint Handling"),
    ("BusinessService:Underwriting Service", "Serving", "BusinessProcess:Risk Evaluation"),
    ("BusinessService:Underwriting Service", "Serving", "BusinessProcess:Premium Calculation"),
    ("BusinessService:Premium Collection Service", "Serving", "BusinessProcess:Broker Commission Settlement"),
    ("BusinessService:Fraud Investigation Service", "Serving", "BusinessProcess:Fraud Detection"),
    ("BusinessService:Regulatory Filing Service", "Serving", "BusinessProcess:Regulatory Reporting"),
    ("BusinessService:Broker Portal Service", "Serving", "BusinessProcess:Broker Commission Settlement"),
    ("BusinessRole:Claims Handler", "Assignment", "BusinessProcess:Claims Registration"),
    ("BusinessRole:Claims Handler", "Assignment", "BusinessProcess:Claims Assessment"),
    ("BusinessRole:Policy Administrator", "Assignment", "BusinessProcess:Policy Issuance"),
    ("BusinessRole:Policy Administrator", "Assignment", "BusinessProcess:Policy Renewal"),
    ("BusinessRole:Risk Analyst", "Assignment", "BusinessProcess:Risk Evaluation"),
    ("BusinessRole:Underwriter", "Assignment", "BusinessProcess:Premium Calculation"),
    ("BusinessRole:Compliance Officer", "Assignment", "BusinessProcess:Regulatory Reporting"),
    ("BusinessRole:IT Service Manager", "Assignment", "BusinessProcess:SLA Monitoring"),
    ("BusinessRole:Data Steward", "Assignment", "BusinessProcess:Fraud Detection"),
    ("BusinessRole:Security Officer", "Assignment", "BusinessProcess:Customer Identity Verification"),
    ("BusinessRole:Customer Service Representative", "Assignment", "BusinessProcess:Complaint Handling"),
    ("BusinessRole:Business Analyst", "Assignment", "BusinessProcess:Document Digitization"),
    # ── Application -> Business ──
    ("ApplicationComponent:CRM System", "Serving", "BusinessProcess:Customer Onboarding"),
    ("ApplicationComponent:CRM System", "Serving", "BusinessProcess:Complaint Handling"),
    ("ApplicationComponent:Policy Administration System", "Serving", "BusinessProcess:Policy Issuance"),
    ("ApplicationComponent:Policy Administration System", "Serving", "BusinessProcess:Policy Renewal"),
    ("ApplicationComponent:Claims Management Platform", "Serving", "BusinessProcess:Claims Registration"),
    ("ApplicationComponent:Claims Management Platform", "Serving", "BusinessProcess:Claims Assessment"),
    ("ApplicationComponent:Risk Engine", "Serving", "BusinessProcess:Risk Evaluation"),
    ("ApplicationComponent:Risk Engine", "Serving", "BusinessProcess:Premium Calculation"),
    ("ApplicationComponent:Customer Self-Service Portal", "Serving", "BusinessActor:Customer"),
    ("ApplicationComponent:Customer Self-Service Portal", "Serving", "BusinessProcess:Complaint Handling"),
    ("ApplicationComponent:Document Management System", "Serving", "BusinessProcess:Document Digitization"),
    ("ApplicationComponent:Document Management System", "Serving", "BusinessProcess:Regulatory Reporting"),
    ("ApplicationComponent:Fraud Detection Engine", "Serving", "BusinessProcess:Fraud Detection"),
    ("ApplicationComponent:Reporting & Analytics Platform", "Serving", "BusinessProcess:Regulatory Reporting"),
    ("ApplicationComponent:Reporting & Analytics Platform", "Serving", "BusinessProcess:SLA Monitoring"),
    ("ApplicationComponent:Billing System", "Serving", "BusinessProcess:Broker Commission Settlement"),
    ("ApplicationComponent:Billing System", "Serving", "BusinessProcess:Premium Calculation"),
    ("ApplicationComponent:Broker Portal", "Serving", "BusinessActor:Broker Network"),
    ("ApplicationComponent:Broker Portal", "Serving", "BusinessProcess:Broker Commission Settlement"),
    ("ApplicationComponent:Identity & Access Management", "Serving", "BusinessProcess:Customer Identity Verification"),
    ("ApplicationComponent:Workflow Engine", "Serving", "BusinessProcess:Claims Assessment"),
    ("ApplicationComponent:Workflow Engine", "Serving", "BusinessProcess:Policy Issuance"),
    # ── Application -> Application ──
    ("ApplicationComponent:Claims Management Platform", "Serving", "ApplicationComponent:Notification Service"),
    ("ApplicationComponent:Risk Engine", "Serving", "ApplicationComponent:Policy Administration System"),
    ("ApplicationComponent:Fraud Detection Engine", "Serving", "ApplicationComponent:Claims Management Platform"),
    ("ApplicationComponent:Enterprise Service Bus", "Serving", "ApplicationComponent:CRM System"),
    ("ApplicationComponent:Enterprise Service Bus", "Serving", "ApplicationComponent:Billing System"),
    ("ApplicationComponent:Enterprise Service Bus", "Serving", "ApplicationComponent:Policy Administration System"),
    ("ApplicationComponent:API Gateway", "Serving", "ApplicationComponent:Customer Self-Service Portal"),
    ("ApplicationComponent:API Gateway", "Serving", "ApplicationComponent:Mobile App Backend"),
    ("ApplicationComponent:API Gateway", "Serving", "ApplicationComponent:Broker Portal"),
    ("ApplicationComponent:Data Warehouse", "Serving", "ApplicationComponent:Reporting & Analytics Platform"),
    ("ApplicationComponent:Batch Processing Engine", "Serving", "ApplicationComponent:Data Warehouse"),
    ("ApplicationComponent:Email Service", "Serving", "ApplicationComponent:Notification Service"),
    ("ApplicationComponent:Content Delivery Network", "Serving", "ApplicationComponent:Customer Self-Service Portal"),
    ("ApplicationComponent:Mobile App Backend", "Serving", "BusinessActor:Customer"),
    # ── Application Service Realization ──
    ("ApplicationService:Claims API", "Realization", "ApplicationComponent:Claims Management Platform"),
    ("ApplicationService:Policy API", "Realization", "ApplicationComponent:Policy Administration System"),
    ("ApplicationService:Risk Scoring API", "Realization", "ApplicationComponent:Risk Engine"),
    ("ApplicationService:Customer API", "Realization", "ApplicationComponent:CRM System"),
    ("ApplicationService:Notification API", "Realization", "ApplicationComponent:Notification Service"),
    ("ApplicationService:Document API", "Realization", "ApplicationComponent:Document Management System"),
    ("ApplicationService:Fraud Scoring API", "Realization", "ApplicationComponent:Fraud Detection Engine"),
    ("ApplicationService:Payment API", "Realization", "ApplicationComponent:Billing System"),
    ("ApplicationService:Reporting API", "Realization", "ApplicationComponent:Reporting & Analytics Platform"),
    ("ApplicationService:Authentication API", "Realization", "ApplicationComponent:Identity & Access Management"),
    # ── Application -> Data ──
    ("ApplicationComponent:CRM System", "Access", "DataObject:Customer Record"),
    ("ApplicationComponent:Policy Administration System", "Access", "DataObject:Policy Record"),
    ("ApplicationComponent:Claims Management Platform", "Access", "DataObject:Claim Record"),
    ("ApplicationComponent:Risk Engine", "Access", "DataObject:Premium Calculation Data"),
    ("ApplicationComponent:Fraud Detection Engine", "Access", "DataObject:Fraud Score Dataset"),
    ("ApplicationComponent:Billing System", "Access", "DataObject:Commission Ledger"),
    ("ApplicationComponent:Reporting & Analytics Platform", "Access", "DataObject:Analytics Cube"),
    ("ApplicationComponent:Document Management System", "Access", "DataObject:Document Metadata"),
    ("ApplicationComponent:Identity & Access Management", "Access", "DataObject:Audit Log"),
    ("ApplicationComponent:Data Warehouse", "Access", "DataObject:Analytics Cube"),
    ("ApplicationComponent:Data Warehouse", "Access", "DataObject:Policy Record"),
    ("ApplicationComponent:Data Warehouse", "Access", "DataObject:Claim Record"),
    ("ApplicationComponent:Reporting & Analytics Platform", "Access", "DataObject:Regulatory Submission Record"),
    # ── Technology -> Application ──
    ("SystemSoftware:Kubernetes", "Assignment", "ApplicationComponent:Claims Management Platform"),
    ("SystemSoftware:Kubernetes", "Assignment", "ApplicationComponent:Risk Engine"),
    ("SystemSoftware:Kubernetes", "Assignment", "ApplicationComponent:Fraud Detection Engine"),
    ("SystemSoftware:Kubernetes", "Assignment", "ApplicationComponent:API Gateway"),
    ("SystemSoftware:Kubernetes", "Assignment", "ApplicationComponent:Notification Service"),
    ("SystemSoftware:Docker Engine", "Assignment", "ApplicationComponent:CRM System"),
    ("SystemSoftware:Docker Engine", "Assignment", "ApplicationComponent:Broker Portal"),
    ("SystemSoftware:Docker Engine", "Assignment", "ApplicationComponent:Mobile App Backend"),
    ("SystemSoftware:PostgreSQL 15", "Serving", "ApplicationComponent:Policy Administration System"),
    ("SystemSoftware:PostgreSQL 15", "Serving", "ApplicationComponent:Claims Management Platform"),
    ("SystemSoftware:PostgreSQL 15", "Serving", "ApplicationComponent:CRM System"),
    ("SystemSoftware:Oracle Database 19c", "Serving", "ApplicationComponent:Billing System"),
    ("SystemSoftware:Oracle Database 19c", "Serving", "ApplicationComponent:Data Warehouse"),
    ("SystemSoftware:Microsoft SQL Server 2022", "Serving", "ApplicationComponent:Reporting & Analytics Platform"),
    ("SystemSoftware:Apache Kafka", "Serving", "ApplicationComponent:Enterprise Service Bus"),
    ("SystemSoftware:Apache Kafka", "Serving", "ApplicationComponent:Batch Processing Engine"),
    ("SystemSoftware:Elasticsearch", "Serving", "ApplicationComponent:Document Management System"),
    ("SystemSoftware:Redis", "Serving", "ApplicationComponent:API Gateway"),
    ("SystemSoftware:Redis", "Serving", "ApplicationComponent:Customer Self-Service Portal"),
    ("SystemSoftware:Nginx", "Serving", "ApplicationComponent:Content Delivery Network"),
    ("SystemSoftware:Nginx", "Serving", "ApplicationComponent:Customer Self-Service Portal"),
    # ── Technology -> Technology ──
    ("Node:App Server Cluster", "Assignment", "SystemSoftware:Kubernetes"),
    ("Node:App Server Cluster", "Assignment", "SystemSoftware:Docker Engine"),
    ("Node:App Server Cluster", "Assignment", "SystemSoftware:Red Hat Linux 9"),
    ("Node:Database Server Primary", "Assignment", "SystemSoftware:PostgreSQL 15"),
    ("Node:Database Server Primary", "Assignment", "SystemSoftware:Oracle Database 19c"),
    ("Node:Database Server Replica", "Assignment", "SystemSoftware:PostgreSQL 15"),
    ("Node:Batch Processing Node", "Assignment", "SystemSoftware:Apache Kafka"),
    ("Node:Log Aggregation Node", "Assignment", "SystemSoftware:Elasticsearch"),
    ("Node:Edge Cache Node", "Assignment", "SystemSoftware:Nginx"),
    ("Node:Edge Cache Node", "Assignment", "SystemSoftware:Redis"),
    ("Node:GPU Analytics Node", "Assignment", "SystemSoftware:Microsoft SQL Server 2022"),
    ("Node:Monitoring Server", "Assignment", "SystemSoftware:Elasticsearch"),
    ("Node:CI/CD Build Server", "Assignment", "SystemSoftware:Docker Engine"),
    ("Node:DR Recovery Node", "Assignment", "SystemSoftware:PostgreSQL 15"),
    ("TechnologyService:Database Service", "Realization", "Node:Database Server Primary"),
    ("TechnologyService:Database Service", "Realization", "Node:Database Server Replica"),
    ("TechnologyService:Container Orchestration", "Realization", "SystemSoftware:Kubernetes"),
    ("TechnologyService:Message Queue Service", "Realization", "SystemSoftware:Apache Kafka"),
    ("TechnologyService:Object Storage Service", "Realization", "Node:Batch Processing Node"),
    ("TechnologyService:Log Aggregation Service", "Realization", "Node:Log Aggregation Node"),
    ("TechnologyService:Secrets Management Service", "Realization", "Device:HSM Appliance"),
    ("TechnologyService:DNS Service", "Realization", "Node:Edge Cache Node"),
    ("TechnologyService:Certificate Management Service", "Realization", "Device:HSM Appliance"),
    # ── Artifact -> Application ──
    ("Artifact:claims-service.jar", "Realization", "ApplicationComponent:Claims Management Platform"),
    ("Artifact:policy-api-v2.war", "Realization", "ApplicationComponent:Policy Administration System"),
    ("Artifact:risk-model-weights.pkl", "Realization", "ApplicationComponent:Risk Engine"),
    ("Artifact:fraud-scoring-model.onnx", "Realization", "ApplicationComponent:Fraud Detection Engine"),
    ("Artifact:notification-worker.jar", "Realization", "ApplicationComponent:Notification Service"),
    ("Artifact:etl-pipeline-config.yaml", "Realization", "ApplicationComponent:Batch Processing Engine"),
    ("Artifact:api-gateway-routes.json", "Realization", "ApplicationComponent:API Gateway"),
    # ── Device -> Node / Network ──
    ("Device:Load Balancer F5", "Assignment", "CommunicationNetwork:DMZ Network"),
    ("Device:Firewall Palo Alto", "Assignment", "CommunicationNetwork:DMZ Network"),
    ("Device:Firewall Palo Alto", "Assignment", "CommunicationNetwork:Corporate LAN"),
    ("Device:SAN Storage Array", "Serving", "Node:Database Server Primary"),
    ("Device:SAN Storage Array", "Serving", "Node:Database Server Replica"),
    ("Device:Backup Tape Library", "Serving", "Node:DR Recovery Node"),
    ("Device:WAN Accelerator", "Assignment", "CommunicationNetwork:Cloud VPN"),
    ("Device:Network Switch Cisco Nexus", "Assignment", "CommunicationNetwork:Corporate LAN"),
    ("Device:Network Switch Cisco Nexus", "Assignment", "CommunicationNetwork:Management VLAN"),
    ("Device:Wireless Access Controller", "Assignment", "CommunicationNetwork:Corporate LAN"),
    # ── Motivation ──
    ("Goal:Reduce Claims Processing Time by 40%", "Influence", "Requirement:Real-time Risk Scoring"),
    ("Goal:Achieve 99.9% System Availability", "Influence", "Requirement:RPO of 15 minutes"),
    ("Goal:Achieve 99.9% System Availability", "Influence", "Requirement:RTO of 1 hour"),
    ("Goal:Zero Data Breaches by 2026", "Influence", "Requirement:Data Encryption at Rest and in Transit"),
    ("Goal:Zero Data Breaches by 2026", "Influence", "Requirement:Role-based Access Control"),
    ("Goal:Achieve Full Regulatory Compliance", "Influence", "Requirement:GDPR Compliance"),
    ("Goal:Achieve Full Regulatory Compliance", "Influence", "Requirement:PCI-DSS Level 1 Certification"),
    ("Goal:Achieve Full Regulatory Compliance", "Influence", "Requirement:SOX Audit Trail"),
    ("Goal:Reduce IT Operational Costs by 25%", "Influence", "Requirement:Sub-second API Response Time"),
    ("Goal:Migrate 100% Workloads to Cloud by 2027", "Influence", "Constraint:Minimum 3 Availability Zones"),
    ("Goal:Automate 80% of Underwriting Decisions", "Influence", "Requirement:Real-time Risk Scoring"),
    ("Stakeholder:CTO", "Association", "Goal:Achieve 99.9% System Availability"),
    ("Stakeholder:CTO", "Association", "Goal:Migrate 100% Workloads to Cloud by 2027"),
    ("Stakeholder:CTO", "Association", "Goal:Reduce IT Operational Costs by 25%"),
    ("Stakeholder:Head of Claims", "Association", "Goal:Reduce Claims Processing Time by 40%"),
    ("Stakeholder:Chief Risk Officer", "Association", "Goal:Increase Customer Satisfaction to NPS 60+"),
    ("Stakeholder:Chief Risk Officer", "Association", "Goal:Zero Data Breaches by 2026"),
    ("Stakeholder:CISO", "Association", "Goal:Zero Data Breaches by 2026"),
    ("Stakeholder:CISO", "Association", "Goal:Achieve Full Regulatory Compliance"),
    ("Stakeholder:CFO", "Association", "Goal:Reduce IT Operational Costs by 25%"),
    ("Stakeholder:Enterprise Architect", "Association", "Goal:Migrate 100% Workloads to Cloud by 2027"),
    ("Stakeholder:Enterprise Architect", "Association", "Goal:Achieve 99.9% System Availability"),
    # ── Capability -> Business ──
    ("Capability:Claims Processing Automation", "Realization", "BusinessProcess:Claims Assessment"),
    ("Capability:Claims Processing Automation", "Realization", "BusinessProcess:Claims Registration"),
    ("Capability:Risk Assessment Intelligence", "Realization", "BusinessProcess:Risk Evaluation"),
    ("Capability:Risk Assessment Intelligence", "Realization", "BusinessProcess:Fraud Detection"),
    ("Capability:Digital Customer Experience", "Realization", "BusinessService:Customer Portal Service"),
    ("Capability:Digital Customer Experience", "Realization", "BusinessService:Broker Portal Service"),
    ("Capability:Omnichannel Distribution", "Realization", "BusinessProcess:Customer Onboarding"),
    ("Capability:Data-Driven Underwriting", "Realization", "BusinessProcess:Premium Calculation"),
    ("Capability:Regulatory Compliance Management", "Realization", "BusinessProcess:Regulatory Reporting"),
    ("Capability:Operational Resilience", "Realization", "BusinessProcess:SLA Monitoring"),
    ("Capability:Cyber Risk Mitigation", "Realization", "BusinessProcess:Customer Identity Verification"),
    ("Capability:Product Innovation", "Realization", "BusinessService:Underwriting Service"),
    ("Capability:Partner Ecosystem Integration", "Realization", "BusinessService:Broker Portal Service"),
    ("Capability:Partner Ecosystem Integration", "Realization", "BusinessProcess:Broker Commission Settlement"),
    # ── Constraint -> Motivation ──
    ("Constraint:Legacy Oracle DB Migration Deadline Q4 2026", "Influence", "Goal:Migrate 100% Workloads to Cloud by 2027"),
    ("Constraint:Budget Cap EUR 2M Annual", "Influence", "Goal:Reduce IT Operational Costs by 25%"),
    ("Constraint:No Public Cloud for PII Data (until 2026 review)", "Influence", "Goal:Achieve Full Regulatory Compliance"),
    ("Constraint:Vendor Lock-in Avoidance", "Influence", "Goal:Migrate 100% Workloads to Cloud by 2027"),
]

# ---------------------------------------------------------------------------
# Entity Alias Map  (canonical -> [aliases])
# Each document randomly picks one alias when referencing the entity.
# ---------------------------------------------------------------------------

ENTITY_ALIASES = {
    # Application Components
    "CRM System": ["Salesforce CRM", "Customer Management Platform", "CRM"],
    "Policy Administration System": ["PAS", "Policy Admin", "Guidewire PolicyCenter"],
    "Claims Management Platform": ["Claims Platform", "CMP", "Claims Processing System"],
    "Risk Engine": ["Risk Scoring Engine", "Actuarial Risk Module", "Risk Calculator"],
    "Customer Self-Service Portal": ["Customer Portal", "Self-Service Web App", "MyArchiSurance Portal"],
    "Document Management System": ["DMS", "Alfresco DMS", "Document Repository"],
    "Fraud Detection Engine": ["Fraud Engine", "Anti-Fraud Module", "FDE"],
    "Reporting & Analytics Platform": ["BI Platform", "Analytics Dashboard", "Cognos Analytics"],
    "Enterprise Service Bus": ["ESB", "Integration Bus", "MuleSoft ESB"],
    "Identity & Access Management": ["IAM", "Access Management System", "Okta IAM"],
    "API Gateway": ["Kong API Gateway", "API Management Layer", "Gateway"],
    "Data Warehouse": ["DWH", "Enterprise Data Warehouse", "Oracle DWH"],
    "Billing System": ["Billing Engine", "Revenue Management System", "Billing"],
    "Notification Service": ["Notification Engine", "Alert Service", "Messaging Service"],
    "Workflow Engine": ["BPM Engine", "Process Automation Engine", "Camunda BPM"],
    # Technology
    "PostgreSQL 15": ["Postgres", "PostgreSQL DB", "the primary relational database"],
    "Oracle Database 19c": ["Oracle DB", "the legacy Oracle database", "Oracle RDBMS"],
    "Kubernetes": ["K8s", "the container orchestration platform", "Kubernetes Cluster"],
    "Apache Kafka": ["Kafka", "the event streaming platform", "Kafka Cluster"],
    "Redis": ["Redis Cache", "the in-memory cache", "Redis Cluster"],
    "Elasticsearch": ["Elastic", "the search engine cluster", "ELK Stack"],
    "Docker Engine": ["Docker", "the container runtime", "Docker CE"],
    # Business
    "Claims Department": ["Claims Division", "Claims Unit", "Claims Dept."],
    "Underwriting Team": ["Underwriting Department", "UW Team", "Underwriting Division"],
    "Customer Onboarding": ["New Customer Registration", "Client Onboarding", "Customer Enrollment"],
    "Claims Registration": ["Claim Intake", "First Notice of Loss", "FNOL Process"],
    "Claims Assessment": ["Claim Evaluation", "Claim Adjudication", "Loss Assessment"],
    "Fraud Detection": ["Fraud Screening", "Anti-Fraud Analysis", "Fraud Check"],
    # Motivation
    "Reduce Claims Processing Time by 40%": ["40% Claims STP Target", "Claims Efficiency Goal"],
    "Achieve 99.9% System Availability": ["Four-Nines Uptime Goal", "99.9% SLA Target"],
    # Infra
    "Load Balancer F5": ["F5 Big-IP", "the load balancer", "F5 LB"],
    "Firewall Palo Alto": ["Palo Alto NGFW", "the perimeter firewall", "PA Firewall"],
    "App Server Cluster": ["Application Server Farm", "Compute Cluster", "App Nodes"],
    "Corporate LAN": ["Internal Network", "Office LAN", "Corporate Ethernet"],
    "DMZ Network": ["Demilitarized Zone", "the DMZ", "Perimeter Network"],
}

# ---------------------------------------------------------------------------
# Utility: pick a name (canonical or random alias) for an entity
# ---------------------------------------------------------------------------

def _name(canonical: str, use_alias: bool = True) -> str:
    """Return canonical name or a random alias if available."""
    if use_alias and canonical in ENTITY_ALIASES:
        return random.choice([canonical] + ENTITY_ALIASES[canonical])
    return canonical


# ---------------------------------------------------------------------------
# Build reverse indexes for quick relationship lookup
# ---------------------------------------------------------------------------

def _rels_where_source(prefix_name):
    return [r for r in RELATIONSHIPS if r[0] == prefix_name]

def _rels_where_target(prefix_name):
    return [r for r in RELATIONSHIPS if r[2] == prefix_name]


# ===========================================================================
# PDF Helper
# ===========================================================================

class DocPDF(FPDF):
    """Extended FPDF with helpers for enterprise-style documents."""

    def __init__(self, title: str, doc_id: str, author: str = "ArchiSurance EA Team"):
        super().__init__()
        self.doc_title = title
        self.doc_id = doc_id
        self.doc_author = author
        self.set_auto_page_break(auto=True, margin=15)
        self.set_left_margin(10)
        self.set_right_margin(10)
        self._w = self.w - self.l_margin - self.r_margin  # effective width

    # --- structural helpers ---

    def title_page(self, subtitle: str = "", version: str = "2.1",
                   classification: str = "INTERNAL - CONFIDENTIAL"):
        self.add_page()
        self.ln(40)
        self.set_font("Helvetica", "B", 26)
        self.multi_cell(self._w, 12, self.doc_title, align="C")
        if subtitle:
            self.set_font("Helvetica", "", 14)
            self.ln(4)
            self.multi_cell(self._w, 8, subtitle, align="C")
        self.ln(20)
        self.set_font("Helvetica", "", 11)
        self.multi_cell(self._w, 7, f"Document ID: {self.doc_id}", align="C")
        self.multi_cell(self._w, 7, f"Version: {version}", align="C")
        self.multi_cell(self._w, 7, f"Author: {self.doc_author}", align="C")
        self.multi_cell(self._w, 7, f"Date: {datetime.now().strftime('%B %d, %Y')}", align="C")
        self.multi_cell(self._w, 7, f"Classification: {classification}", align="C")
        self.ln(30)
        self.set_font("Helvetica", "I", 9)
        self.multi_cell(self._w, 5,
            "This document is the property of ArchiSurance B.V. and contains "
            "confidential information. Unauthorized reproduction or distribution "
            "is prohibited. For questions contact the Enterprise Architecture team "
            "at ea-team@archisurance.example.com.", align="C")

    def version_history(self, entries=None):
        if entries is None:
            entries = [
                ("0.1", "2024-01-15", "J. van den Berg", "Initial draft"),
                ("0.5", "2024-03-22", "M. de Vries", "Peer review incorporated"),
                ("1.0", "2024-06-10", "P. Jansen", "Approved by Architecture Board"),
                ("1.5", "2024-11-04", "J. van den Berg", "Updated for Q4 changes"),
                ("2.0", "2025-02-18", "M. de Vries", "Annual revision"),
                ("2.1", "2025-04-01", "P. Jansen", "Minor corrections"),
            ]
        self.add_page()
        self.h2("Document Version History")
        self.ln(4)
        col_w = [15, 25, 40, self._w - 80]
        headers = ["Ver.", "Date", "Author", "Description"]
        self.set_font("Helvetica", "B", 9)
        for i, h in enumerate(headers):
            self.cell(col_w[i], 7, h, border=1)
        self.ln()
        self.set_font("Helvetica", "", 9)
        for ver, date, author, desc in entries:
            self.cell(col_w[0], 6, ver, border=1)
            self.cell(col_w[1], 6, date, border=1)
            self.cell(col_w[2], 6, author, border=1)
            self.cell(col_w[3], 6, desc, border=1)
            self.ln()
        self.ln(6)

    def toc(self, items):
        """Simple table of contents."""
        self.add_page()
        self.h2("Table of Contents")
        self.ln(4)
        self.set_font("Helvetica", "", 10)
        for num, title in items:
            dots = "." * max(2, 70 - len(f"{num} {title}"))
            self.cell(self._w, 6, f"{num}  {title}  {dots}  {num.split('.')[0]}")
            self.ln()
        self.ln(6)

    # --- text helpers ---

    def h1(self, text):
        self.ln(6)
        self.set_font("Helvetica", "B", 16)
        self.multi_cell(self._w, 10, text)
        self.set_font("Helvetica", "", 10)
        self.ln(2)

    def h2(self, text):
        self.ln(4)
        self.set_font("Helvetica", "B", 13)
        self.multi_cell(self._w, 8, text)
        self.set_font("Helvetica", "", 10)
        self.ln(1)

    def h3(self, text):
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.multi_cell(self._w, 7, text)
        self.set_font("Helvetica", "", 10)
        self.ln(1)

    def para(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(self._w, 5, text)
        self.ln(3)

    def bullet(self, text):
        self.set_font("Helvetica", "", 10)
        self.cell(6, 5, "-")
        self.multi_cell(self._w - 6, 5, text)
        self.ln(1)

    def code_block(self, text):
        self.set_font("Courier", "", 8)
        self.set_fill_color(240, 240, 240)
        for line in text.split("\n"):
            self.cell(self._w, 4, line, fill=True)
            self.ln()
        self.set_font("Helvetica", "", 10)
        self.ln(3)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [self._w / len(headers)] * len(headers)
        self.set_font("Helvetica", "B", 9)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=1)
        self.ln()
        self.set_font("Helvetica", "", 8)
        for row in rows:
            max_h = 6
            for i, cell_text in enumerate(row):
                self.cell(col_widths[i], max_h, str(cell_text)[:int(col_widths[i]/2)], border=1)
            self.ln()
        self.ln(4)

    def noise_meeting_notes(self):
        """Insert realistic meeting notes that are NOT ArchiMate content."""
        self.h3("Appendix: Meeting Minutes - Architecture Review Board")
        self.para(
            "Date: March 15, 2025. Location: ArchiSurance HQ, Room 4.12. "
            "Attendees: J. van den Berg (chair), M. de Vries, P. Jansen, K. Bakker, "
            "S. Visser, T. Mulder (remote). Apologies: R. de Jong (on leave)."
        )
        self.para(
            "Agenda item 1: Review of open action items from previous meeting. "
            "Action 2024-47 (Jansen): Provide updated cost estimate for Oracle migration. "
            "Status: Completed. The revised estimate is EUR 1.4M including contingency. "
            "Action 2024-48 (de Vries): Schedule penetration test with external vendor. "
            "Status: In progress, vendor shortlist reduced to two candidates."
        )
        self.para(
            "Agenda item 2: Discussion on coffee machine replacement in the 3rd floor "
            "kitchen. The current Jura E8 has been experiencing frequent bean grinder "
            "failures. Facilities will procure a replacement by end of month. Not related "
            "to architecture but raised due to impact on team productivity during long "
            "review sessions."
        )
        self.para(
            "Agenda item 3: Parking lot discussion about whether to adopt Backstage as "
            "the internal developer portal. Deferred to next meeting pending PoC results. "
            "K. Bakker noted that the onboarding documentation is outdated and should be "
            "refreshed regardless of the portal decision."
        )
        self.para(
            "Next meeting: April 12, 2025 at 14:00 CET. Van den Berg to circulate "
            "agenda by April 5."
        )

    def noise_disclaimer(self):
        self.ln(4)
        self.set_font("Helvetica", "I", 8)
        self.multi_cell(self._w, 4,
            "DISCLAIMER: This document has been prepared for internal use by ArchiSurance B.V. "
            "The information contained herein is provided on an 'as-is' basis without warranties "
            "of any kind, either express or implied. ArchiSurance B.V. shall not be liable for "
            "any direct, indirect, incidental, or consequential damages arising from the use of "
            "this document. The views expressed herein are those of the Enterprise Architecture "
            "team and do not necessarily reflect the official position of the Board of Directors. "
            "All trademarks mentioned belong to their respective owners. This document may contain "
            "forward-looking statements that involve risks and uncertainties. Actual results may "
            "differ materially from those projected. Recipients are advised to seek independent "
            "professional advice before acting on any information contained in this document."
        )
        self.set_font("Helvetica", "", 10)
        self.ln(4)

    def noise_acronym_glossary(self):
        self.h3("Glossary of Acronyms")
        acronyms = [
            ("API", "Application Programming Interface"),
            ("BPM", "Business Process Management"),
            ("CDN", "Content Delivery Network"),
            ("CISO", "Chief Information Security Officer"),
            ("CRM", "Customer Relationship Management"),
            ("DR", "Disaster Recovery"),
            ("DMS", "Document Management System"),
            ("DMZ", "Demilitarized Zone"),
            ("EA", "Enterprise Architecture"),
            ("ESB", "Enterprise Service Bus"),
            ("ETL", "Extract, Transform, Load"),
            ("FNOL", "First Notice of Loss"),
            ("GDPR", "General Data Protection Regulation"),
            ("HSM", "Hardware Security Module"),
            ("IAM", "Identity and Access Management"),
            ("KPI", "Key Performance Indicator"),
            ("LAN", "Local Area Network"),
            ("MTTR", "Mean Time to Recovery"),
            ("NPS", "Net Promoter Score"),
            ("PAS", "Policy Administration System"),
            ("PCI-DSS", "Payment Card Industry Data Security Standard"),
            ("PoC", "Proof of Concept"),
            ("RBAC", "Role-Based Access Control"),
            ("RPO", "Recovery Point Objective"),
            ("RTO", "Recovery Time Objective"),
            ("SAN", "Storage Area Network"),
            ("SLA", "Service Level Agreement"),
            ("SOX", "Sarbanes-Oxley Act"),
            ("STP", "Straight-Through Processing"),
            ("VLAN", "Virtual Local Area Network"),
            ("VPN", "Virtual Private Network"),
            ("WAN", "Wide Area Network"),
        ]
        col_w = [25, self._w - 25]
        self.set_font("Helvetica", "B", 9)
        self.cell(col_w[0], 7, "Acronym", border=1)
        self.cell(col_w[1], 7, "Definition", border=1)
        self.ln()
        self.set_font("Helvetica", "", 8)
        for acr, defn in acronyms:
            self.cell(col_w[0], 5, acr, border=1)
            self.cell(col_w[1], 5, defn, border=1)
            self.ln()
        self.ln(4)

    def noise_references(self):
        """Insert a references section with related documents -- pure noise."""
        self.h3("References and Related Documents")
        refs = [
            ("EA-OVR-001", "Enterprise Architecture Overview", "3.0"),
            ("EA-APP-002", "Application Portfolio & Inventory", "4.2"),
            ("EA-INFRA-003", "Infrastructure Design Document", "2.5"),
            ("EA-BIZ-004", "CRM Business Process Description", "2.0"),
            ("EA-CLM-005", "Claims Processing Workflow", "3.1"),
            ("EA-SEC-006", "Security Architecture", "2.3"),
            ("EA-INT-007", "Integration Architecture", "2.8"),
            ("EA-DAT-008", "Data Architecture & Governance", "2.0"),
            ("EA-CLD-009", "Cloud Migration Assessment", "1.5"),
            ("EA-DR-010", "Disaster Recovery & Business Continuity Plan", "3.0"),
            ("EA-NET-011", "Network Architecture", "2.2"),
            ("EA-ROAD-012", "Strategic IT Roadmap 2025-2027", "2.0"),
            ("EA-SVC-013", "IT Service Catalog", "3.5"),
            ("EA-VND-014", "Vendor & Technology Assessment", "1.8"),
            ("EA-OPS-015", "Operational Runbook: Core Platform", "4.1"),
            ("EA-CMP-016", "Compliance & Regulatory Requirements", "2.5"),
            ("EA-CHG-017", "Change Management: ERP Migration", "1.2"),
        ]
        col_w = [25, 55, self._w - 80]
        self.set_font("Helvetica", "B", 9)
        self.cell(col_w[0], 7, "Doc ID", border=1)
        self.cell(col_w[1], 7, "Title", border=1)
        self.cell(col_w[2], 7, "Version", border=1)
        self.ln()
        self.set_font("Helvetica", "", 8)
        for doc_id, title, ver in refs:
            self.cell(col_w[0], 5, doc_id, border=1)
            self.cell(col_w[1], 5, title[:35], border=1)
            self.cell(col_w[2], 5, ver, border=1)
            self.ln()
        self.ln(4)

    def noise_distribution_list(self):
        """Insert a document distribution list -- pure noise."""
        self.h3("Distribution List")
        dist = [
            ("J. van den Berg", "Enterprise Architect", "Review & Approve"),
            ("M. de Vries", "Application Architect", "Review & Contribute"),
            ("P. Jansen", "Integration Architect", "Review & Contribute"),
            ("K. Bakker", "Infrastructure Architect", "Review & Contribute"),
            ("S. Visser", "Business Analyst", "Inform"),
            ("T. Mulder", "Process Architect", "Inform"),
            ("R. de Jong", "CISO", "Review & Approve"),
            ("L. Hendriks", "Data Architect", "Inform"),
            ("A. Willems", "CTO", "Final Approval"),
            ("B. Smit", "Head of Claims", "Business Sign-off"),
        ]
        col_w = [35, 40, self._w - 75]
        self.set_font("Helvetica", "B", 9)
        self.cell(col_w[0], 7, "Name", border=1)
        self.cell(col_w[1], 7, "Role", border=1)
        self.cell(col_w[2], 7, "Responsibility", border=1)
        self.ln()
        self.set_font("Helvetica", "", 8)
        for name, role, resp in dist:
            self.cell(col_w[0], 5, name, border=1)
            self.cell(col_w[1], 5, role, border=1)
            self.cell(col_w[2], 5, resp, border=1)
            self.ln()
        self.ln(4)

    def noise_revision_notes(self):
        """Insert a detailed revision notes section."""
        self.h3("Detailed Revision Notes for Version 2.1")
        self.para(
            "Section 2.3 was updated to reflect the new naming convention adopted by the "
            "Platform Engineering team. All references to 'microservice cluster' have been "
            "replaced with 'application workload group' per the Architecture Board decision "
            "of January 2025. Section 4.1 was expanded to include the results of the "
            "capacity planning exercise conducted in Q4 2024, which identified the need for "
            "additional compute resources in the Amsterdam primary data center."
        )
        self.para(
            "Appendix B was added to include the RACI matrix requested by the PMO during "
            "the Q3 2024 quarterly review. The glossary was updated to include twelve new "
            "acronyms that were introduced since the previous version. Figure 3 was replaced "
            "with an updated diagram generated from the Sparx EA repository on March 28, 2025. "
            "The document classification was elevated from 'Internal' to 'Internal - Confidential' "
            "following the data classification review of February 2025."
        )
        self.para(
            "Feedback from the peer review conducted by M. de Vries on March 10, 2025, "
            "addressed three items: (1) clarification of the boundary between the DMZ and "
            "the application tier, (2) addition of the backup retention policy reference, "
            "and (3) correction of the SLA target for the Claims Handling Service from "
            "99.5% to 99.9% as agreed in the contract amendment of December 2024."
        )


# ===========================================================================
# DOCUMENT GENERATORS (17 documents)
# Each returns a built DocPDF ready to output.
# ===========================================================================

# ---- helpers for filler prose ----

_FILLER_POOL_A = [
    "has been a critical area of focus for ArchiSurance since the digital transformation initiative began in 2023",
    "Stakeholders across multiple departments have contributed requirements for this workstream",
    "The architecture decisions were reviewed and approved by the Architecture Review Board in Q2 2024",
    "Implementation follows an iterative approach, with quarterly milestones aligned to the overall program timeline",
    "Risk mitigation strategies include regular checkpoint reviews, automated regression testing, and staged rollout procedures",
    "The design considers both current-state constraints and target-state aspirations as documented in the strategic roadmap",
    "Cross-functional workshops held in January and March 2025 helped refine the scope and integration points",
    "Budget allocation was approved as part of the annual IT investment portfolio review conducted in November 2024",
    "Change management activities include stakeholder communication, training sessions, and documentation updates",
    "The operational support model is defined in the Operational Runbook and includes on-call rotation and escalation procedures",
    "Performance benchmarks are captured in the enterprise monitoring framework and reported on a monthly basis to leadership",
    "Lessons learned from the pilot phase have been incorporated into the current design iteration",
    "External consultants from Deloitte provided an independent assessment of the architecture in late 2024",
    "The initiative is tracked in the enterprise PMO tool with bi-weekly status updates to the steering committee",
    "Security review was completed in accordance with the CISO's security-by-design framework",
    "Integration testing spans three environments: development, staging, and pre-production",
    "Data privacy impact assessment was filed with the Data Protection Officer in Q1 2025",
    "The vendor selection process followed the procurement guidelines established by the CFO's office",
    "Automated deployment pipelines leverage the CI/CD infrastructure described in the platform engineering documentation",
    "Monitoring and alerting are integrated with the central observability stack based on Prometheus and Grafana",
]

_FILLER_POOL_B = [
    "During the initial assessment phase, the team identified several areas where the existing architecture fell short of the target-state requirements defined in the enterprise roadmap",
    "The Architecture Review Board convened a special session in February 2025 to evaluate the implications of the proposed changes on downstream systems and business processes",
    "A proof-of-concept was conducted over a four-week period, involving representatives from the Claims Department, IT Operations, and the Data Analytics Team to validate the technical feasibility",
    "The total cost of ownership analysis, prepared by the Finance Department in collaboration with IT, indicated a payback period of approximately eighteen months assuming current utilization rates",
    "The transition plan was developed in alignment with the enterprise change management framework, incorporating staged rollouts, parallel-run periods, and defined go/no-go criteria at each milestone",
    "Capacity planning exercises revealed that the current infrastructure can sustain projected growth for the next twelve months, after which additional compute and storage resources will be required",
    "The solution was designed to be modular, allowing individual components to be upgraded or replaced without affecting the overall system availability or data integrity",
    "A comprehensive training program was developed for end users, including online modules, instructor-led sessions, and a sandbox environment for hands-on practice",
    "The project governance structure includes a steering committee meeting monthly, a working group meeting weekly, and daily stand-ups during active development sprints",
    "Dependencies on third-party services were documented and risk-assessed, with fallback mechanisms defined for each critical integration point",
    "The operational acceptance criteria include automated smoke tests, performance baselines, runbook completeness, and sign-off from both the IT Service Manager and the business process owner",
    "Post-implementation review sessions are scheduled for thirty and ninety days after go-live to capture lessons learned and identify optimization opportunities",
    "The architecture team maintains a dependency register that maps each component to its upstream providers and downstream consumers, updated quarterly",
    "Service-level indicators are collected continuously and aggregated into dashboards visible to both technical teams and business stakeholders",
    "The data classification exercise, completed in Q4 2024, assigned sensitivity labels to all data objects, informing encryption, access control, and retention policies",
    "An internal audit in March 2025 confirmed that the controls implemented for this area meet the requirements of the enterprise risk management framework",
    "The platform engineering team provides a standardized deployment template that all application teams are required to use, ensuring consistency in logging, health checks, and resource limits",
    "A dedicated Slack channel was established for real-time coordination between development, operations, and security teams during the rollout period",
    "The enterprise architecture repository in Sparx EA is the authoritative source for all model elements; any changes to this document must be reflected there within five business days",
    "Regression test suites are maintained by the QA team and executed automatically on every merge to the main branch via the CI/CD pipeline",
]

_FILLER_POOL_C = [
    "From a historical perspective, ArchiSurance first recognized the need for modernization in this area following an internal efficiency review conducted in late 2022, which highlighted significant manual effort and process duplication across regional offices",
    "The architectural principles that guide this work include separation of concerns, loose coupling between components, preference for open standards, and the ability to scale horizontally under peak load conditions such as end-of-year policy renewals",
    "Collaboration with the vendor support team has been essential during the implementation phase; weekly technical syncs ensure that configuration changes are validated against the vendor's reference architecture before being applied to the production environment",
    "The enterprise data model, maintained by the Data Architecture team, defines canonical schemas for all shared data objects; integrating systems are expected to conform to these schemas or implement transformation layers that map proprietary formats to the canonical model",
    "Business continuity considerations were incorporated from the outset, with the DR Recovery Node in the secondary data center providing failover capacity; the most recent failover test was conducted in October 2024 and achieved recovery within the target RTO of one hour",
    "The solution leverages event-driven patterns wherever possible, with Apache Kafka providing durable, ordered event streams that decouple producers from consumers and enable replay for debugging and reprocessing scenarios",
    "Compliance with the General Data Protection Regulation requires that personally identifiable information is encrypted at rest and in transit, with access restricted to authorized roles as defined in the Identity and Access Management policy",
    "Feedback from the user acceptance testing phase indicated that the new interface reduced the average task completion time by approximately thirty percent compared to the legacy system, though some users requested additional keyboard shortcuts for power-user workflows",
    "The architecture team conducted a threat modeling exercise using the STRIDE framework, identifying potential spoofing, tampering, and information disclosure risks; mitigations for each threat were documented and tracked in the security risk register",
    "Interoperability with partner systems is achieved through the Partner Integration Hub, which exposes a curated subset of the internal API surface with additional rate limiting, schema validation, and audit logging applied at the gateway layer",
    "The migration strategy follows a strangler-fig pattern, where new functionality is built in the target platform while legacy features are gradually redirected; this approach minimizes disruption to active users and allows incremental validation of the new implementation",
    "Key performance indicators for the initiative include transaction throughput, error rate, mean time to detection, mean time to recovery, and user satisfaction scores collected through quarterly surveys",
    "The enterprise technology radar, published semi-annually by the CTO's office, classifies technologies as Adopt, Trial, Assess, or Hold; the technologies used in this area are all currently in the Adopt or Trial rings",
    "Technical debt in this area was cataloged during a dedicated sprint in Q3 2024; the resulting backlog of forty-seven items has been prioritized by business impact and is being addressed alongside feature development",
    "The non-functional requirements specify a maximum end-to-end latency of five hundred milliseconds at the ninety-ninth percentile, measured under a sustained load of one thousand concurrent users",
    "Documentation standards require that all architecture decisions are recorded as Architecture Decision Records using the ADR format proposed by Michael Nygard, stored alongside the codebase in the version control system",
    "The team uses a definition of done that includes code review by at least two peers, passing CI pipeline, updated architecture diagrams, and entry in the change log maintained by the Release Manager",
    "Scalability testing performed in the staging environment confirmed that the system handles a three-times-peak load without degradation, providing sufficient headroom for seasonal demand fluctuations",
    "The observability strategy follows the three pillars model: structured logs shipped to Elasticsearch, distributed traces collected via OpenTelemetry, and metrics scraped by Prometheus; all three are unified in Grafana dashboards",
    "An accessibility audit was conducted by an external specialist in January 2025 to ensure that all user-facing components meet WCAG 2.1 Level AA standards, with remediation items tracked in the product backlog",
]

_FILLER_POOL_D = [
    "The information security team requires that all new systems undergo a penetration test before production deployment, with findings above medium severity remediated prior to go-live approval",
    "Capacity forecasting models project a twenty-five percent year-over-year increase in data volume, driven primarily by the digitization of paper-based processes and the expansion of the broker channel",
    "A chaos engineering program was introduced in Q1 2025, starting with controlled fault injection in the staging environment to validate the resilience of the system against network partitions and dependency failures",
    "The architecture review confirmed that the proposed solution aligns with the TOGAF Architecture Development Method phases used by ArchiSurance, specifically phases B through D covering Business, Information Systems, and Technology Architecture",
    "The development team follows trunk-based development with short-lived feature branches, automated linting, and a code coverage threshold of eighty percent enforced by the CI pipeline",
    "In the context of insurance operations, peak load occurs during natural disaster events when claim submissions can spike by up to ten times the normal rate; the auto-scaling configuration accounts for this burst pattern",
    "The data retention policy mandates that transactional records are kept for seven years in online storage and archived to cold storage thereafter, with the ability to retrieve archived records within twenty-four hours upon regulatory request",
    "The network team conducted a bandwidth utilization study in February 2025, confirming that inter-datacenter traffic remains below sixty percent of the available WAN capacity under normal operating conditions",
    "ArchiSurance participates in an industry-wide information sharing and analysis center for insurance companies, contributing anonymized threat intelligence data and receiving early warnings about sector-specific attack patterns",
    "The API design guidelines specify that all REST endpoints must support content negotiation, return standard HTTP status codes, include correlation identifiers in response headers, and provide machine-readable error bodies in RFC 7807 format",
    "Deployment windows are scheduled every Tuesday and Thursday between 06:00 and 08:00 CET, with emergency deployments requiring approval from both the IT Service Manager and the on-call engineer",
    "The business process documentation follows the BPMN 2.0 standard, with process models maintained in the Signavio process modeling tool and linked to the ArchiMate model elements in Sparx EA",
    "A formal lessons-learned workshop is held at the end of each quarter, with outcomes published to the internal wiki and action items assigned to specific team members with target completion dates",
    "The vendor risk assessment framework evaluates suppliers across five dimensions: financial stability, technology roadmap alignment, support quality, security posture, and contractual flexibility",
    "The enterprise identity provider federates with the national eHerkenning system for business-to-government interactions and with DigiD for customer-facing authentication on the self-service portal",
    "Application health is assessed using a synthetic monitoring approach, where automated scripts simulate real user journeys every five minutes and report availability from three geographically distributed probe locations",
    "The configuration management database maintains a record of all IT assets, including hardware serial numbers, software license keys, patch levels, and relationships between configuration items",
    "Cost allocation for shared infrastructure follows a chargeback model based on resource consumption metrics, with monthly reports sent to each business unit for transparency and accountability",
    "The incident management process defines four severity levels, with Severity 1 incidents requiring a response within fifteen minutes and a post-incident review within five business days",
    "The enterprise backup strategy uses a 3-2-1 approach: three copies of data, on two different media types, with one copy stored offsite at the secondary data center in Rotterdam",
]


def _filler(topic, sentences=8):
    """Generate filler prose to pad documents to realistic length.

    Draws from four pools of ~20 sentences each (80 total) to avoid repetition
    across documents and sections.
    """
    pool_a = [f"The {topic} {s}." if s[0].islower() else f"{s}." if not s.endswith(".") else s
              for s in _FILLER_POOL_A]
    pool_b = [f"{s}." if not s.endswith(".") else s for s in _FILLER_POOL_B]
    pool_c = [f"{s}." if not s.endswith(".") else s for s in _FILLER_POOL_C]
    pool_d = [f"{s}." if not s.endswith(".") else s for s in _FILLER_POOL_D]
    all_fillers = pool_a + pool_b + pool_c + pool_d
    # If requesting more sentences than available, allow repeats from different pools
    if sentences > len(all_fillers):
        chosen = all_fillers[:]
        random.shuffle(chosen)
    else:
        chosen = random.sample(all_fillers, min(sentences, len(all_fillers)))
    return " ".join(chosen)


def _long_para(topic, min_sentences=5, max_sentences=10):
    """Generate a longer realistic paragraph (~15-25 sentences).

    The min/max parameters from callers are scaled up to produce substantial
    blocks of text that result in 15-40 page documents.
    """
    # Scale up to produce much more text per call
    count = random.randint(min_sentences * 3, max_sentences * 3)
    return _filler(topic, min(count, 70))


def _enterprise_prose(pdf, topic, paragraphs=4, sentences_per_para=8):
    """Write multiple paragraphs of enterprise prose directly to the PDF.

    This is the main mechanism for padding documents to realistic page counts.
    Each call produces substantial content that reads like real IT documentation.
    """
    for _ in range(paragraphs):
        pdf.para(_filler(topic, sentences_per_para))


def _section_prose(pdf, topic):
    """Standard enterprise prose block: 3 paragraphs of 8-10 sentences each.

    Call this after every major section to ensure realistic document length.
    """
    _enterprise_prose(pdf, topic, 3, random.randint(8, 10))


# ---- Per-document entity tracking ----
_doc_entities = {}  # doc_id -> set of canonical entity names

def _track(doc_id, canonical):
    """Record that a canonical entity appears in a document."""
    _doc_entities.setdefault(doc_id, set()).add(canonical)

def _use(doc_id, canonical):
    """Return an alias for the entity and track it."""
    _track(doc_id, canonical)
    return _name(canonical)


# ===== Document 01: Enterprise Architecture Overview =====

def gen_doc_01():
    doc_id = "doc_01"
    pdf = DocPDF("ArchiSurance Enterprise Architecture Overview",
                 "EA-OVR-001", "J. van den Berg, Enterprise Architect")
    pdf.title_page("An integrated view across all ArchiMate layers", "3.0")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction and Scope"),
        ("2", "Strategic Layer"),
        ("3", "Business Layer Overview"),
        ("4", "Application Layer Overview"),
        ("5", "Technology Layer Overview"),
        ("6", "Motivation and Goals"),
        ("7", "Cross-Layer Dependencies"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction and Scope")
    pdf.para(
        "ArchiSurance B.V. is a mid-size insurance company headquartered in Amsterdam, "
        "operating across the Benelux region with approximately 2,400 employees. The company "
        "offers life, non-life, and health insurance products through direct and broker channels. "
        "This document provides a comprehensive overview of the enterprise architecture, "
        "structured according to the ArchiMate 3.2 modeling standard. It serves as the "
        "single source of truth for understanding how strategy, business operations, applications, "
        "and technology infrastructure relate to one another."
    )
    pdf.para(
        "The scope of this document encompasses all five ArchiMate layers: Strategy, Business, "
        "Application, Technology, and Motivation. For detailed descriptions of individual layers, "
        "readers are referred to the companion documents in the EA document suite. In particular, "
        "the Application Portfolio and Inventory document (EA-APP-002) provides an exhaustive "
        "catalog of all application components, while the Infrastructure Design Document "
        "(EA-INFRA-003) covers the technology layer in depth."
    )
    pdf.para(_long_para("enterprise architecture overview"))
    _enterprise_prose(pdf, "enterprise architecture overview", 4, 10)

    pdf.h2("1.1 Document Conventions and Intended Audience")
    pdf.para(
        "This document is intended for enterprise architects, solution architects, and senior "
        "IT management. It uses ArchiMate 3.2 notation throughout. Entities are referenced by "
        "their canonical names as defined in the EA repository. Where an entity has commonly "
        "used alternative names, these are noted in parentheses on first occurrence. Diagrams "
        "referenced in this document are maintained in the Sparx EA model repository and are "
        "not reproduced here to avoid version skew."
    )
    _enterprise_prose(pdf, "document conventions", 3, 8)

    # Strategy Layer
    pdf.h1("2. Strategic Layer")
    pdf.para(
        "ArchiSurance's strategic architecture is built around ten core capabilities that "
        "underpin the digital transformation program launched in 2023. Each capability maps "
        "to one or more business processes and services, ensuring traceability from strategic "
        "intent to operational execution."
    )
    for cap in ENTITIES["Capability"]:
        _track(doc_id, cap)
        pdf.h3(_use(doc_id, cap))
        realizes = [r for r in RELATIONSHIPS if r[0] == f"Capability:{cap}"]
        targets = [r[2].split(":")[1] for r in realizes]
        for t in targets:
            _track(doc_id, t)
        if targets:
            pdf.para(
                f"The {_name(cap)} capability realizes the following business elements: "
                f"{', '.join(_name(t) for t in targets)}. "
                f"This capability has been prioritized as part of the 2025-2027 strategic roadmap "
                f"and is currently in the implementation phase with expected completion by Q3 2026."
            )
        else:
            pdf.para(
                f"The {_name(cap)} capability is a foundational element of the enterprise "
                f"architecture. Detailed realization mappings are under development."
            )
        pdf.para(_filler(cap, 6))
        _enterprise_prose(pdf, cap, 2, 8)

    _enterprise_prose(pdf, "strategic capabilities", 3, 10)

    # Business Layer
    pdf.h1("3. Business Layer Overview")
    pdf.para(
        "The business layer describes the organizational structure, key processes, and services "
        "that ArchiSurance delivers. As described in the CRM Business Process Description "
        "(EA-BIZ-004) and the Claims Processing Workflow document (EA-CLM-005), the core "
        "insurance value chain consists of customer onboarding, underwriting, policy issuance, "
        "claims handling, and renewal management."
    )
    for actor in ENTITIES["BusinessActor"]:
        _track(doc_id, actor)
        pdf.bullet(f"{_use(doc_id, actor)} -- organizational unit participating in insurance operations.")
    pdf.ln(4)
    pdf.para(
        "Business roles define the responsibilities within each unit. The following roles "
        "have been identified and mapped to processes:"
    )
    for role in ENTITIES["BusinessRole"]:
        _track(doc_id, role)
        assigned = [r[2].split(":")[1] for r in RELATIONSHIPS
                    if r[0] == f"BusinessRole:{role}" and r[1] == "Assignment"]
        for a in assigned:
            _track(doc_id, a)
        pdf.bullet(
            f"{role} -- assigned to: {', '.join(_name(a) for a in assigned) if assigned else 'multiple processes'}."
        )
    pdf.ln(4)
    pdf.para(
        "The key business processes are summarized below. For detailed swimlane diagrams "
        "and RACI matrices, refer to the dedicated process documents."
    )
    for proc in ENTITIES["BusinessProcess"][:8]:
        _track(doc_id, proc)
        pdf.bullet(f"{_use(doc_id, proc)}")
    pdf.para(_long_para("business architecture", 5, 8))
    _enterprise_prose(pdf, "business layer architecture", 4, 10)

    pdf.h2("3.1 Business Objects and Contracts")
    for obj in ENTITIES["BusinessObject"]:
        _track(doc_id, obj)
        pdf.bullet(f"{obj} -- core information asset managed across the enterprise.")
    pdf.ln(4)
    for c in ENTITIES["Contract"]:
        _track(doc_id, c)
        pdf.bullet(f"{c} -- governs operational commitments between parties.")
    _enterprise_prose(pdf, "business objects and contracts", 3, 8)

    # Application Layer
    pdf.h1("4. Application Layer Overview")
    pdf.para(
        "ArchiSurance maintains a portfolio of twenty application components, ten application "
        "services, and five application interfaces. The Application Portfolio and Inventory "
        "document (EA-APP-002) provides the definitive catalog. Key systems include:"
    )
    for app in ENTITIES["ApplicationComponent"]:
        _track(doc_id, app)
        pdf.bullet(f"{_use(doc_id, app)}")
    pdf.para(_long_para("application landscape", 4, 7))
    _enterprise_prose(pdf, "application landscape overview", 4, 10)

    # Technology Layer
    pdf.h1("5. Technology Layer Overview")
    pdf.para(
        "The technology layer supports the application portfolio through a hybrid "
        "infrastructure spanning on-premises data centers and cloud services. Details "
        "are provided in the Infrastructure Design Document (EA-INFRA-003). The core "
        "components include:"
    )
    for node in ENTITIES["Node"]:
        _track(doc_id, node)
        pdf.bullet(f"{_use(doc_id, node)}")
    for sw in ENTITIES["SystemSoftware"][:6]:
        _track(doc_id, sw)
        pdf.bullet(f"{_use(doc_id, sw)}")
    pdf.para(_long_para("technology infrastructure", 5, 8))
    _enterprise_prose(pdf, "technology infrastructure overview", 4, 10)

    # Motivation
    pdf.h1("6. Motivation and Goals")
    pdf.para(
        "The motivation layer captures the strategic drivers, goals, and constraints "
        "that shape architectural decisions. These are elaborated in the Strategic IT "
        "Roadmap (EA-ROAD-012)."
    )
    for goal in ENTITIES["Goal"]:
        _track(doc_id, goal)
        pdf.h3(_use(doc_id, goal))
        stakeholders = [r[0].split(":")[1] for r in RELATIONSHIPS
                        if r[2] == f"Goal:{goal}" and r[1] == "Association"]
        for s in stakeholders:
            _track(doc_id, s)
        pdf.para(
            f"Championed by: {', '.join(stakeholders) if stakeholders else 'multiple stakeholders'}. "
            f"This goal directly influences architectural decisions around system design, "
            f"technology selection, and resource allocation."
        )
        pdf.para(_filler(goal, 5))
        _enterprise_prose(pdf, goal, 2, 8)

    for req in ENTITIES["Requirement"]:
        _track(doc_id, req)
    for con in ENTITIES["Constraint"]:
        _track(doc_id, con)
    for sh in ENTITIES["Stakeholder"]:
        _track(doc_id, sh)

    pdf.para(
        "Requirements and constraints are detailed in Section 6 of this document. Key requirements "
        f"include: {', '.join(_use(doc_id, r) for r in ENTITIES['Requirement'][:5])}. "
        f"Architectural constraints include: {', '.join(_use(doc_id, c) for c in ENTITIES['Constraint'][:3])}."
    )

    # Cross-layer dependencies
    pdf.h1("7. Cross-Layer Dependencies")
    pdf.para(
        "The value of the ArchiMate model lies in the traceability it provides across layers. "
        "For example, the goal to Reduce Claims Processing Time by 40% is championed by the "
        f"Head of Claims, drives the requirement for {_use(doc_id, 'Real-time Risk Scoring')}, "
        f"which is realized by the {_use(doc_id, 'Risk Engine')}, deployed on "
        f"{_use(doc_id, 'Kubernetes')}, running on the {_use(doc_id, 'App Server Cluster')}. "
        "This chain demonstrates how a strategic goal traces through business, application, "
        "and technology layers."
    )
    pdf.para(_long_para("cross-layer dependency analysis", 6, 10))
    _enterprise_prose(pdf, "cross-layer dependency analysis", 5, 10)

    # Noise appendices
    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 02: Application Portfolio & Inventory =====

def gen_doc_02():
    doc_id = "doc_02"
    pdf = DocPDF("Application Portfolio & Inventory",
                 "EA-APP-002", "M. de Vries, Application Architect")
    pdf.title_page("Complete catalog of ArchiSurance application components", "4.2")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Application Component Catalog"),
        ("3", "Application Services"),
        ("4", "Application Interfaces"),
        ("5", "Data Objects"),
        ("6", "Integration Map"),
        ("7", "Ownership and Support Matrix"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document provides the definitive catalog of all application components, services, "
        "interfaces, and data objects within the ArchiSurance enterprise. It is maintained by "
        "the Application Architecture team and updated quarterly. The Enterprise Architecture "
        "Overview (EA-OVR-001) provides context on how these applications fit within the broader "
        "architecture. For infrastructure details supporting these applications, refer to the "
        "Infrastructure Design Document (EA-INFRA-003)."
    )
    pdf.para(_long_para("application portfolio management", 5, 8))
    _enterprise_prose(pdf, "application portfolio management", 4, 10)

    pdf.h1("2. Application Component Catalog")
    pdf.para(
        "ArchiSurance operates twenty application components ranging from legacy systems "
        "to modern cloud-native microservices. Each component is described below with its "
        "business alignment, technology dependencies, and data access patterns."
    )

    for app in ENTITIES["ApplicationComponent"]:
        _track(doc_id, app)
        pdf.h2(f"2.x {_use(doc_id, app)}")

        # Business processes served
        serves_biz = [r[2].split(":")[1] for r in RELATIONSHIPS
                      if r[0] == f"ApplicationComponent:{app}" and r[1] == "Serving"
                      and "BusinessProcess:" in r[2]]
        for s in serves_biz:
            _track(doc_id, s)

        # Data accessed
        accesses = [r[2].split(":")[1] for r in RELATIONSHIPS
                    if r[0] == f"ApplicationComponent:{app}" and r[1] == "Access"]
        for a in accesses:
            _track(doc_id, a)

        # Tech dependencies
        tech_deps = [r[0].split(":")[1] for r in RELATIONSHIPS
                     if r[2] == f"ApplicationComponent:{app}"
                     and r[0].split(":")[0] in ("SystemSoftware", "Node")]
        for t in tech_deps:
            _track(doc_id, t)

        # App-to-app
        app_serves = [r[2].split(":")[1] for r in RELATIONSHIPS
                      if r[0] == f"ApplicationComponent:{app}" and r[1] == "Serving"
                      and "ApplicationComponent:" in r[2]]
        for a in app_serves:
            _track(doc_id, a)

        pdf.para(
            f"The {_name(app)} is a core component of the ArchiSurance application landscape. "
            f"It was first deployed in {'2018' if 'Legacy' in app or 'Oracle' in app else '2022'} "
            f"and has undergone multiple iterations since then. The system is classified as "
            f"{'Tier 1 (business critical)' if app in ['Claims Management Platform', 'Policy Administration System', 'CRM System', 'Risk Engine'] else 'Tier 2 (important)'} "
            f"in the application tiering framework."
        )
        if serves_biz:
            pdf.para(f"Business processes served: {', '.join(_name(s) for s in serves_biz)}.")
        if accesses:
            pdf.para(f"Data objects accessed: {', '.join(_name(a) for a in accesses)}.")
        if tech_deps:
            pdf.para(f"Technology dependencies: {', '.join(_name(t) for t in tech_deps)}.")
        if app_serves:
            pdf.para(f"Downstream application consumers: {', '.join(_name(a) for a in app_serves)}.")

        pdf.para(_filler(app, 6))
        _enterprise_prose(pdf, app, 2, 8)

    # Application Services
    pdf.h1("3. Application Services")
    pdf.para(
        "Application services represent the externally visible behavior of application components. "
        "Each service is exposed through one or more interfaces and realized by specific components."
    )
    for svc in ENTITIES["ApplicationService"]:
        _track(doc_id, svc)
        realized_by = [r[2].split(":")[1] for r in RELATIONSHIPS
                       if r[0] == f"ApplicationService:{svc}" and r[1] == "Realization"]
        for rb in realized_by:
            _track(doc_id, rb)
        pdf.h3(svc)
        pdf.para(
            f"The {svc} is realized by: {', '.join(_name(rb) for rb in realized_by) if realized_by else 'TBD'}. "
            f"This service is exposed via the {_use(doc_id, 'REST API Gateway')} and authenticated "
            f"through the {_use(doc_id, 'Identity & Access Management')} platform."
        )
        _track(doc_id, "REST API Gateway")
        _track(doc_id, "Identity & Access Management")
        pdf.para(_filler(svc, 5))
        _enterprise_prose(pdf, svc, 1, 8)

    # Interfaces
    pdf.h1("4. Application Interfaces")
    for iface in ENTITIES["ApplicationInterface"]:
        _track(doc_id, iface)
        pdf.h3(iface)
        pdf.para(
            f"The {iface} provides external connectivity for partners, customers, and internal "
            f"consumers. As described in the Integration Architecture document (EA-INT-007), "
            f"all interfaces are secured with TLS 1.3 and require OAuth 2.0 bearer tokens."
        )
        pdf.para(_filler(iface, 5))

    # Data Objects
    pdf.h1("5. Data Objects")
    for dobj in ENTITIES["DataObject"]:
        _track(doc_id, dobj)
        accessed_by = [r[0].split(":")[1] for r in RELATIONSHIPS
                       if r[2] == f"DataObject:{dobj}" and r[1] == "Access"]
        for ab in accessed_by:
            _track(doc_id, ab)
        pdf.h3(dobj)
        pdf.para(
            f"The {dobj} is a critical data asset. It is accessed by: "
            f"{', '.join(_name(ab) for ab in accessed_by) if accessed_by else 'multiple systems'}. "
            f"Data governance policies for this object are described in the Data Architecture "
            f"and Governance document (EA-DAT-008)."
        )
        pdf.para(_filler(dobj, 5))

    # Ownership matrix table
    pdf.add_page()
    pdf.h1("6. Integration Map")
    pdf.para(
        "The integration map shows data flows between application components. The "
        f"{_use(doc_id, 'Enterprise Service Bus')} serves as the primary integration backbone, "
        f"complemented by the {_use(doc_id, 'API Gateway')} for RESTful interactions."
    )
    _track(doc_id, "Enterprise Service Bus")
    _track(doc_id, "API Gateway")
    pdf.para(_long_para("application integration", 6, 10))
    _enterprise_prose(pdf, "application integration patterns", 4, 10)

    pdf.h1("7. Ownership and Support Matrix")
    headers = ["Application", "Owner", "Tier", "Support Team"]
    rows = []
    owners = ["Claims IT", "Policy IT", "Platform Eng", "Data Team", "Infra Ops", "Security"]
    for i, app in enumerate(ENTITIES["ApplicationComponent"]):
        rows.append([
            app[:25],
            owners[i % len(owners)],
            "T1" if i < 5 else "T2",
            f"Team-{chr(65 + i % 6)}"
        ])
    pdf.table(headers, rows, [50, 30, 15, self_w := 190 - 95])
    _enterprise_prose(pdf, "application ownership and support", 3, 10)

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 03: Infrastructure Design Document =====

def gen_doc_03():
    doc_id = "doc_03"
    pdf = DocPDF("Infrastructure Design Document",
                 "EA-INFRA-003", "K. Bakker, Infrastructure Architect")
    pdf.title_page("Servers, networks, storage and platform services", "2.5")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Compute Infrastructure"),
        ("3", "System Software Stack"),
        ("4", "Network Architecture"),
        ("5", "Storage and Backup"),
        ("6", "Technology Services"),
        ("7", "Deployment Artifacts"),
        ("8", "Server Inventory"),
        ("9", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the technology infrastructure that underpins the ArchiSurance "
        "application portfolio. It covers compute nodes, system software, network topology, "
        "storage architecture, and deployment artifacts. For the application-level view, refer "
        "to the Application Portfolio and Inventory (EA-APP-002). The Disaster Recovery and "
        "Business Continuity Plan (EA-DR-010) details failover procedures for the infrastructure "
        "described herein."
    )
    pdf.para(_long_para("infrastructure design", 6, 9))
    _enterprise_prose(pdf, "infrastructure design", 4, 10)

    pdf.h1("2. Compute Infrastructure")
    pdf.para("ArchiSurance operates ten compute nodes across two data centers and one cloud region:")
    for node in ENTITIES["Node"]:
        _track(doc_id, node)
        pdf.h3(_use(doc_id, node))
        assigned = [r[2].split(":")[1] for r in RELATIONSHIPS
                    if r[0] == f"Node:{node}" and r[1] == "Assignment"]
        for a in assigned:
            _track(doc_id, a)
        if assigned:
            pdf.para(f"Hosts: {', '.join(_name(a) for a in assigned)}.")
        pdf.para(
            f"The {_name(node)} is located in the primary Amsterdam data center (AMS-DC1). "
            f"It consists of {'16' if 'Cluster' in node else '8'} vCPU cores and "
            f"{'64' if 'Cluster' in node else '32'} GB RAM. Hardware refresh is scheduled "
            f"for Q2 2026 as part of the infrastructure modernization program."
        )
        pdf.para(_filler(node, 6))
        _enterprise_prose(pdf, node, 2, 8)

    _enterprise_prose(pdf, "compute infrastructure", 3, 10)

    pdf.h1("3. System Software Stack")
    for sw in ENTITIES["SystemSoftware"]:
        _track(doc_id, sw)
        pdf.h3(_use(doc_id, sw))
        serves = [r[2].split(":")[1] for r in RELATIONSHIPS
                  if r[0] == f"SystemSoftware:{sw}" and r[1] in ("Serving", "Assignment")]
        for s in serves:
            _track(doc_id, s)
        if serves:
            pdf.para(f"Supports: {', '.join(_name(s) for s in serves)}.")
        hosted_on = [r[0].split(":")[1] for r in RELATIONSHIPS
                     if r[2] == f"SystemSoftware:{sw}" and r[1] == "Assignment"]
        for h in hosted_on:
            _track(doc_id, h)
        if hosted_on:
            pdf.para(f"Deployed on: {', '.join(_name(h) for h in hosted_on)}.")
        pdf.para(_filler(sw, 4))

    # Config snippet for Kubernetes
    pdf.h3("Kubernetes Cluster Configuration (excerpt)")
    pdf.code_block(textwrap.dedent("""\
        apiVersion: v1
        kind: Namespace
        metadata:
          name: archisurance-prod
          labels:
            env: production
            team: platform-engineering
        ---
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: claims-service
          namespace: archisurance-prod
        spec:
          replicas: 3
          selector:
            matchLabels:
              app: claims-service
          template:
            spec:
              containers:
              - name: claims-service
                image: registry.archisurance.internal/claims-service:2.4.1
                resources:
                  requests:
                    memory: "512Mi"
                    cpu: "500m"
                  limits:
                    memory: "1Gi"
                    cpu: "1000m"
                ports:
                - containerPort: 8080"""))

    pdf.h1("4. Network Architecture")
    pdf.para(
        "The network architecture is organized into four segments as described in the "
        "Network Architecture document (EA-NET-011). Traffic between segments is controlled "
        "by the firewall appliances."
    )
    for net in ENTITIES["CommunicationNetwork"]:
        _track(doc_id, net)
        pdf.h3(_use(doc_id, net))
        devices = [r[0].split(":")[1] for r in RELATIONSHIPS
                   if r[2] == f"CommunicationNetwork:{net}" and r[1] == "Assignment"]
        for d in devices:
            _track(doc_id, d)
        if devices:
            pdf.para(f"Connected devices: {', '.join(_name(d) for d in devices)}.")
        pdf.para(_filler(net, 6))
        _enterprise_prose(pdf, net, 2, 8)

    _enterprise_prose(pdf, "network segmentation architecture", 3, 10)

    pdf.h1("5. Storage and Backup")
    for dev in ENTITIES["Device"]:
        _track(doc_id, dev)
        pdf.h3(_use(doc_id, dev))
        serves = [r[2].split(":")[1] for r in RELATIONSHIPS
                  if r[0] == f"Device:{dev}" and r[1] in ("Serving", "Assignment")]
        for s in serves:
            _track(doc_id, s)
        if serves:
            pdf.para(f"Serves/connects: {', '.join(_name(s) for s in serves)}.")
        pdf.para(_filler(dev, 5))
        _enterprise_prose(pdf, dev, 1, 8)

    _enterprise_prose(pdf, "storage and backup infrastructure", 3, 10)

    pdf.h1("6. Technology Services")
    for tsvc in ENTITIES["TechnologyService"]:
        _track(doc_id, tsvc)
        pdf.h3(tsvc)
        realized_by = [r[2].split(":")[1] for r in RELATIONSHIPS
                       if r[0] == f"TechnologyService:{tsvc}" and r[1] == "Realization"]
        for rb in realized_by:
            _track(doc_id, rb)
        if realized_by:
            pdf.para(f"Realized by: {', '.join(_name(rb) for rb in realized_by)}.")
        pdf.para(_filler(tsvc, 5))
        _enterprise_prose(pdf, tsvc, 1, 8)

    pdf.h1("7. Deployment Artifacts")
    for art in ENTITIES["Artifact"]:
        _track(doc_id, art)
        pdf.h3(art)
        realizes = [r[2].split(":")[1] for r in RELATIONSHIPS
                    if r[0] == f"Artifact:{art}" and r[1] == "Realization"]
        for rl in realizes:
            _track(doc_id, rl)
        if realizes:
            pdf.para(f"Realizes: {', '.join(_name(rl) for rl in realizes)}.")
        pdf.para(_filler(art, 5))

    # Server inventory table
    pdf.add_page()
    pdf.h1("8. Server Inventory")
    headers = ["Hostname", "Role", "CPU", "RAM", "OS", "DC"]
    rows = [
        ["ams-app-01..04", "App Cluster", "16 vCPU", "64 GB", "RHEL 9", "AMS-DC1"],
        ["ams-db-01", "DB Primary", "32 vCPU", "128 GB", "RHEL 9", "AMS-DC1"],
        ["ams-db-02", "DB Replica", "32 vCPU", "128 GB", "RHEL 9", "AMS-DC2"],
        ["ams-batch-01", "Batch Proc", "8 vCPU", "32 GB", "RHEL 9", "AMS-DC1"],
        ["ams-ci-01", "CI/CD Build", "8 vCPU", "16 GB", "RHEL 9", "AMS-DC1"],
        ["ams-mon-01", "Monitoring", "4 vCPU", "16 GB", "RHEL 9", "AMS-DC1"],
        ["ams-log-01", "Log Aggreg", "8 vCPU", "32 GB", "RHEL 9", "AMS-DC1"],
        ["ams-dr-01", "DR Recovery", "16 vCPU", "64 GB", "RHEL 9", "AMS-DC2"],
        ["ams-edge-01", "Edge Cache", "4 vCPU", "8 GB", "RHEL 9", "AMS-DC1"],
        ["ams-gpu-01", "Analytics", "8 vCPU+GPU", "64 GB", "RHEL 9", "AMS-DC1"],
    ]
    w_each = pdf._w / len(headers)
    pdf.table(headers, rows, [w_each]*len(headers))
    _enterprise_prose(pdf, "server inventory management", 3, 10)

    pdf.add_page()
    pdf.h1("9. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 04: CRM Business Process Description =====

def gen_doc_04():
    doc_id = "doc_04"
    pdf = DocPDF("CRM Business Process Description",
                 "EA-BIZ-004", "S. Visser, Business Analyst")
    pdf.title_page("Customer onboarding, case management, and complaint handling", "2.0")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Customer Onboarding Process"),
        ("3", "Customer Identity Verification"),
        ("4", "Complaint Handling Process"),
        ("5", "CRM System Integration"),
        ("6", "Roles and Responsibilities"),
        ("7", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the business processes centered around customer relationship "
        "management at ArchiSurance. It covers customer onboarding, identity verification, "
        "and complaint handling. These processes are supported primarily by the "
        f"{_use(doc_id, 'CRM System')}, with additional support from the "
        f"{_use(doc_id, 'Customer Self-Service Portal')} and the "
        f"{_use(doc_id, 'Identity & Access Management')} platform."
    )
    pdf.para(
        "For the claims-specific workflows that follow customer onboarding, refer to the "
        "Claims Processing Workflow document (EA-CLM-005). The integration patterns between "
        "the CRM and other systems are described in the Integration Architecture (EA-INT-007)."
    )
    pdf.para(_long_para("CRM processes", 6, 10))
    _section_prose(pdf, "CRM business processes")

    # Customer Onboarding
    pdf.h1("2. Customer Onboarding Process")
    _track(doc_id, "Customer Onboarding")
    _track(doc_id, "Customer")
    _track(doc_id, "Sales Division")
    _track(doc_id, "Broker Network")
    _track(doc_id, "Call Center")
    pdf.para(
        f"The {_use(doc_id, 'Customer Onboarding')} process is the entry point for all new "
        f"customers, whether they arrive through the {_use(doc_id, 'Sales Division')}, the "
        f"{_use(doc_id, 'Broker Network')}, or the {_use(doc_id, 'Call Center')}. The process "
        f"begins when a prospective customer expresses interest in an ArchiSurance product and "
        f"ends when a policy has been issued or the application has been declined."
    )
    pdf.para(
        f"Step 1: The {_use(doc_id, 'Customer Service Representative')} or broker enters the "
        f"customer's basic information into the {_use(doc_id, 'CRM System')}. This creates a "
        f"new {_use(doc_id, 'Customer Record')} in the system."
    )
    _track(doc_id, "Customer Service Representative")
    _track(doc_id, "Customer Record")
    pdf.para(
        f"Step 2: The process triggers {_use(doc_id, 'Customer Identity Verification')}, which "
        f"is handled by the {_use(doc_id, 'Identity & Access Management')} platform. This step "
        f"includes KYC (Know Your Customer) checks and sanctions screening."
    )
    _track(doc_id, "Customer Identity Verification")
    pdf.para(
        f"Step 3: Upon successful verification, the {_use(doc_id, 'Customer Onboarding')} "
        f"process triggers {_use(doc_id, 'Policy Issuance')}. The customer's data flows from "
        f"the {_use(doc_id, 'CRM System')} to the {_use(doc_id, 'Policy Administration System')} "
        f"via the {_use(doc_id, 'Enterprise Service Bus')}."
    )
    _track(doc_id, "Policy Issuance")
    _track(doc_id, "Policy Administration System")
    _track(doc_id, "Enterprise Service Bus")
    pdf.para(_long_para("customer onboarding", 6, 10))
    _section_prose(pdf, "customer onboarding workflow")

    # Identity Verification
    pdf.h1("3. Customer Identity Verification")
    _track(doc_id, "Security Officer")
    pdf.para(
        f"The {_use(doc_id, 'Customer Identity Verification')} sub-process is a regulatory "
        f"requirement under GDPR and anti-money laundering (AML) directives. It is overseen by "
        f"the {_use(doc_id, 'Security Officer')} role and implemented through the "
        f"{_use(doc_id, 'Identity & Access Management')} platform."
    )
    pdf.para(
        "The verification process includes: document upload (passport or national ID), "
        "automated optical character recognition, database cross-reference with government "
        "registries, and a risk-based scoring that determines whether manual review is required. "
        "High-risk applications are escalated to the compliance team."
    )
    pdf.para(_long_para("identity verification", 6, 10))
    _section_prose(pdf, "identity verification KYC")

    # Complaint Handling
    pdf.h1("4. Complaint Handling Process")
    _track(doc_id, "Complaint Handling")
    _track(doc_id, "Complaint Ticket")
    _track(doc_id, "SLA Monitoring")
    pdf.para(
        f"The {_use(doc_id, 'Complaint Handling')} process manages all customer complaints "
        f"received through any channel. Each complaint creates a {_use(doc_id, 'Complaint Ticket')} "
        f"in the {_use(doc_id, 'CRM System')}. Resolution progress is tracked against SLAs "
        f"defined in the {_use(doc_id, 'SLA Premium Support')} contract. The "
        f"{_use(doc_id, 'SLA Monitoring')} process ensures timely resolution."
    )
    _track(doc_id, "SLA Premium Support")
    pdf.para(
        f"The {_use(doc_id, 'Customer Self-Service Portal')} allows customers to file and "
        f"track complaints online. The {_use(doc_id, 'Call Center')} handles phone-based "
        f"complaints. Both channels feed into the same CRM workflow."
    )
    pdf.para(_long_para("complaint handling", 6, 10))
    _section_prose(pdf, "complaint handling resolution")

    # CRM Integration
    pdf.h1("5. CRM System Integration")
    _track(doc_id, "Customer API")
    _track(doc_id, "Notification Service")
    _track(doc_id, "Email Service")
    pdf.para(
        f"The {_use(doc_id, 'CRM System')} integrates with the following systems via the "
        f"{_use(doc_id, 'Enterprise Service Bus')}: the {_use(doc_id, 'Policy Administration System')} "
        f"for policy data synchronization, the {_use(doc_id, 'Billing System')} for payment "
        f"status, and the {_use(doc_id, 'Notification Service')} for customer communications. "
        f"The {_use(doc_id, 'Customer API')} provides the external interface for the portal and mobile app."
    )
    _track(doc_id, "Billing System")
    pdf.para(_long_para("CRM integration", 5, 8))
    _section_prose(pdf, "CRM system integration patterns")

    # Roles
    pdf.h1("6. Roles and Responsibilities")
    crm_roles = ["Customer Service Representative", "Policy Administrator", "Compliance Officer", "Security Officer", "Business Analyst"]
    for role in crm_roles:
        _track(doc_id, role)
        pdf.h3(role)
        pdf.para(
            f"The {role} participates in the CRM-related processes as defined in the RACI matrix. "
            f"Detailed role descriptions are maintained in the HR system."
        )
        pdf.para(_filler(role, 8))
    _section_prose(pdf, "roles and responsibilities RACI")

    pdf.add_page()
    pdf.h1("7. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 05: Claims Processing Workflow =====

def gen_doc_05():
    doc_id = "doc_05"
    pdf = DocPDF("Claims Processing Workflow",
                 "EA-CLM-005", "T. Mulder, Process Architect")
    pdf.title_page("Detailed process flow with actors and system support", "3.1")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Claims Registration (FNOL)"),
        ("3", "Claims Assessment"),
        ("4", "Fraud Detection"),
        ("5", "Premium Recalculation"),
        ("6", "Notification and Settlement"),
        ("7", "Process KPIs"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the end-to-end claims processing workflow at ArchiSurance, "
        "from first notice of loss (FNOL) through assessment, fraud screening, and settlement. "
        "The process involves multiple actors and is supported by several application components "
        "as described in the Application Portfolio (EA-APP-002). The CRM Business Process "
        "Description (EA-BIZ-004) covers the upstream customer interaction processes."
    )
    pdf.para(_long_para("claims processing", 6, 10))
    _section_prose(pdf, "claims processing workflow")

    # Claims Registration
    pdf.h1("2. Claims Registration (FNOL)")
    _track(doc_id, "Claims Registration")
    _track(doc_id, "Claims Department")
    _track(doc_id, "Claims Handler")
    _track(doc_id, "Claims Management Platform")
    _track(doc_id, "Claim Record")
    _track(doc_id, "Customer")
    _track(doc_id, "Customer Self-Service Portal")
    _track(doc_id, "CRM System")
    pdf.para(
        f"The {_use(doc_id, 'Claims Registration')} process, also known as First Notice of Loss "
        f"(FNOL), is the starting point of all claims. It is performed by the "
        f"{_use(doc_id, 'Claims Department')} with the {_use(doc_id, 'Claims Handler')} role "
        f"responsible for data entry and initial triage."
    )
    pdf.para(
        f"The {_use(doc_id, 'Customer')} can submit a claim through the "
        f"{_use(doc_id, 'Customer Self-Service Portal')} or by calling the "
        f"{_use(doc_id, 'Call Center')}. In both cases, a new {_use(doc_id, 'Claim Record')} "
        f"is created in the {_use(doc_id, 'Claims Management Platform')}. The system retrieves "
        f"the customer's profile from the {_use(doc_id, 'CRM System')} to pre-populate the form."
    )
    _track(doc_id, "Call Center")
    pdf.para(
        f"Upon registration, the process automatically triggers the "
        f"{_use(doc_id, 'Claims Assessment')} phase. The {_use(doc_id, 'Notification Service')} "
        f"sends a confirmation to the customer via email and SMS."
    )
    _track(doc_id, "Claims Assessment")
    _track(doc_id, "Notification Service")
    pdf.para(_long_para("claims registration FNOL", 6, 10))
    _section_prose(pdf, "FNOL claims registration")

    # Claims Assessment
    pdf.h1("3. Claims Assessment")
    _track(doc_id, "Workflow Engine")
    _track(doc_id, "Document Management System")
    _track(doc_id, "Risk Engine")
    _track(doc_id, "Claims Handling Service")
    pdf.para(
        f"The {_use(doc_id, 'Claims Assessment')} process evaluates each claim against the "
        f"policy terms, damage evidence, and historical patterns. The {_use(doc_id, 'Claims Handler')} "
        f"reviews the claim details in the {_use(doc_id, 'Claims Management Platform')}, which "
        f"orchestrates the assessment workflow through the {_use(doc_id, 'Workflow Engine')}."
    )
    pdf.para(
        f"Supporting documents (photos, police reports, invoices) are stored in the "
        f"{_use(doc_id, 'Document Management System')}. The {_use(doc_id, 'Risk Engine')} "
        f"provides an automated damage estimate based on the claim type and historical data. "
        f"The {_use(doc_id, 'Claims Handling Service')} exposes the assessment capabilities "
        f"to internal and external consumers."
    )
    pdf.para(
        f"Assessment outcomes: (1) Approved -- claim is paid in full, (2) Partially approved -- "
        f"claim is reduced based on policy terms, (3) Rejected -- claim does not meet policy "
        f"criteria, (4) Escalated to fraud -- suspicious patterns detected."
    )
    pdf.para(_long_para("claims assessment adjudication", 6, 10))
    _section_prose(pdf, "claims assessment adjudication")

    # Fraud Detection
    pdf.h1("4. Fraud Detection")
    _track(doc_id, "Fraud Detection")
    _track(doc_id, "Fraud Detection Engine")
    _track(doc_id, "Fraud Score Dataset")
    _track(doc_id, "Data Analytics Team")
    _track(doc_id, "Data Steward")
    _track(doc_id, "Fraud Alert")
    pdf.para(
        f"The {_use(doc_id, 'Fraud Detection')} process is triggered automatically after "
        f"{_use(doc_id, 'Claims Assessment')} when the claim amount exceeds EUR 10,000 or "
        f"when the {_use(doc_id, 'Risk Engine')} flags anomalous patterns. The "
        f"{_use(doc_id, 'Fraud Detection Engine')} applies machine learning models to score "
        f"each claim against the {_use(doc_id, 'Fraud Score Dataset')}."
    )
    pdf.para(
        f"The {_use(doc_id, 'Data Analytics Team')} maintains the fraud detection models, "
        f"with the {_use(doc_id, 'Data Steward')} role responsible for data quality. When a "
        f"claim is flagged, a {_use(doc_id, 'Fraud Alert')} is generated and routed to the "
        f"special investigations unit."
    )
    pdf.para(_long_para("fraud detection screening", 6, 10))
    _section_prose(pdf, "fraud detection ML screening")

    # Premium Recalculation
    pdf.h1("5. Premium Recalculation")
    _track(doc_id, "Premium Calculation")
    _track(doc_id, "Underwriting Team")
    _track(doc_id, "Underwriter")
    _track(doc_id, "Policy Administration System")
    _track(doc_id, "Policy Record")
    _track(doc_id, "Premium Calculation Data")
    _track(doc_id, "Risk Score")
    pdf.para(
        f"After {_use(doc_id, 'Claims Assessment')}, the claim outcome flows to the "
        f"{_use(doc_id, 'Premium Calculation')} process. This process, performed by the "
        f"{_use(doc_id, 'Underwriting Team')} through the {_use(doc_id, 'Underwriter')} role, "
        f"determines whether the customer's premium needs adjustment based on the claim history."
    )
    pdf.para(
        f"The {_use(doc_id, 'Risk Engine')} provides the updated {_use(doc_id, 'Risk Score')}, "
        f"and the {_use(doc_id, 'Policy Administration System')} updates the "
        f"{_use(doc_id, 'Policy Record')} with the recalculated {_use(doc_id, 'Premium Calculation Data')}."
    )
    pdf.para(_long_para("premium recalculation", 5, 8))

    # Notification and Settlement
    pdf.h1("6. Notification and Settlement")
    _track(doc_id, "Billing System")
    _track(doc_id, "Insurance Policy Service")
    _track(doc_id, "Email Service")
    pdf.para(
        f"Once the claim decision is finalized, the {_use(doc_id, 'Notification Service')} "
        f"sends the outcome to the customer via the {_use(doc_id, 'Email Service')} and push "
        f"notification. Payment is processed through the {_use(doc_id, 'Billing System')}. "
        f"The {_use(doc_id, 'Insurance Policy Service')} updates the policy status."
    )
    pdf.para(_long_para("claims settlement notification", 5, 8))
    _section_prose(pdf, "claims settlement payment notification")

    # KPIs
    pdf.h1("7. Process KPIs")
    kpi_headers = ["KPI", "Target", "Current", "Trend"]
    kpi_rows = [
        ["FNOL to Assessment", "< 24 hours", "18 hours", "Improving"],
        ["Assessment to Decision", "< 5 days", "4.2 days", "Stable"],
        ["Fraud Detection Rate", "> 95%", "92%", "Improving"],
        ["STP Rate", "> 60%", "54%", "Improving"],
        ["Customer Satisfaction", "> 4.0/5", "3.8/5", "Stable"],
        ["Claims Reopening Rate", "< 5%", "6.1%", "Degrading"],
    ]
    pdf.table(kpi_headers, kpi_rows, [45, 35, 35, pdf._w - 115])
    _section_prose(pdf, "claims KPI performance management")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 06: Security Architecture =====

def gen_doc_06():
    doc_id = "doc_06"
    pdf = DocPDF("Security Architecture",
                 "EA-SEC-006", "R. de Jong, CISO")
    pdf.title_page("Firewalls, IAM, encryption, and compliance", "2.3")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Perimeter Security"),
        ("3", "Identity and Access Management"),
        ("4", "Data Encryption"),
        ("5", "Security Monitoring"),
        ("6", "Compliance Requirements"),
        ("7", "Security Architecture Decisions"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the security architecture of ArchiSurance, covering perimeter "
        "defenses, identity management, data protection, and compliance with regulatory frameworks. "
        "The security architecture is aligned with the strategic goal to "
        f"{_use(doc_id, 'Zero Data Breaches by 2026')} championed by the "
        f"{_use(doc_id, 'CISO')} and the {_use(doc_id, 'Chief Risk Officer')}."
    )
    _track(doc_id, "Zero Data Breaches by 2026")
    _track(doc_id, "CISO")
    _track(doc_id, "Chief Risk Officer")
    pdf.para(
        "For the network topology referenced in this document, see the Network Architecture "
        "document (EA-NET-011). Infrastructure details are in the Infrastructure Design "
        "Document (EA-INFRA-003)."
    )
    pdf.para(_long_para("security architecture", 6, 10))
    _section_prose(pdf, "security architecture design")

    # Perimeter
    pdf.h1("2. Perimeter Security")
    _track(doc_id, "Firewall Palo Alto")
    _track(doc_id, "Load Balancer F5")
    _track(doc_id, "DMZ Network")
    _track(doc_id, "Corporate LAN")
    _track(doc_id, "API Gateway")
    _track(doc_id, "Content Delivery Network")
    pdf.para(
        f"The perimeter is protected by the {_use(doc_id, 'Firewall Palo Alto')}, a "
        f"next-generation firewall deployed at the boundary between the {_use(doc_id, 'DMZ Network')} "
        f"and the {_use(doc_id, 'Corporate LAN')}. The {_use(doc_id, 'Load Balancer F5')} "
        f"sits in the DMZ and terminates TLS connections before forwarding traffic to the "
        f"{_use(doc_id, 'API Gateway')}."
    )
    pdf.para(
        f"The {_use(doc_id, 'Content Delivery Network')} serves static assets from edge locations "
        f"and includes DDoS mitigation capabilities. All inbound traffic passes through WAF rules "
        f"configured on the {_use(doc_id, 'Load Balancer F5')} before reaching application servers."
    )
    pdf.para(_long_para("perimeter security", 6, 10))
    _section_prose(pdf, "perimeter security defenses")

    # IAM
    pdf.h1("3. Identity and Access Management")
    _track(doc_id, "Identity & Access Management")
    _track(doc_id, "Authentication API")
    _track(doc_id, "Audit Log")
    _track(doc_id, "Customer Identity Verification")
    pdf.para(
        f"The {_use(doc_id, 'Identity & Access Management')} platform provides centralized "
        f"authentication and authorization for all ArchiSurance systems. It exposes the "
        f"{_use(doc_id, 'Authentication API')} for single sign-on (SSO) and multi-factor "
        f"authentication (MFA). All authentication events are logged in the "
        f"{_use(doc_id, 'Audit Log')} data object."
    )
    pdf.para(
        f"Role-based access control (RBAC) is enforced across all application components. "
        f"The {_use(doc_id, 'Customer Identity Verification')} process described in the CRM "
        f"Business Process Description (EA-BIZ-004) uses the same IAM platform for KYC checks."
    )
    pdf.para(_long_para("identity access management", 6, 10))
    _section_prose(pdf, "identity access management SSO MFA")

    # Encryption
    pdf.h1("4. Data Encryption")
    _track(doc_id, "HSM Appliance")
    _track(doc_id, "Data Encryption at Rest and in Transit")
    _track(doc_id, "Secrets Management Service")
    _track(doc_id, "Certificate Management Service")
    _track(doc_id, "PostgreSQL 15")
    _track(doc_id, "Oracle Database 19c")
    pdf.para(
        f"All data at rest is encrypted using AES-256 with keys managed by the "
        f"{_use(doc_id, 'HSM Appliance')}. The {_use(doc_id, 'Secrets Management Service')} "
        f"and {_use(doc_id, 'Certificate Management Service')} both rely on the HSM for "
        f"cryptographic operations. Database-level encryption is enabled on "
        f"{_use(doc_id, 'PostgreSQL 15')} (transparent data encryption) and "
        f"{_use(doc_id, 'Oracle Database 19c')} (Oracle Advanced Security)."
    )
    pdf.para(
        f"All data in transit is protected by TLS 1.3. The requirement for "
        f"{_use(doc_id, 'Data Encryption at Rest and in Transit')} is driven by the GDPR "
        f"Compliance and PCI-DSS Level 1 Certification requirements."
    )
    _track(doc_id, "GDPR Compliance")
    _track(doc_id, "PCI-DSS Level 1 Certification")
    pdf.para(_long_para("data encryption", 6, 10))
    _section_prose(pdf, "data encryption TLS AES key management")

    # Monitoring
    pdf.h1("5. Security Monitoring")
    _track(doc_id, "Elasticsearch")
    _track(doc_id, "Log Aggregation Service")
    _track(doc_id, "Monitoring Server")
    _track(doc_id, "Log Aggregation Node")
    pdf.para(
        f"Security events are collected by the {_use(doc_id, 'Log Aggregation Service')}, "
        f"running on the {_use(doc_id, 'Log Aggregation Node')} and the "
        f"{_use(doc_id, 'Monitoring Server')}. The {_use(doc_id, 'Elasticsearch')} cluster "
        f"indexes all security logs for real-time threat detection and forensic analysis."
    )
    pdf.para(_long_para("security monitoring SIEM", 6, 10))
    _section_prose(pdf, "security monitoring SIEM alerting")

    # Compliance
    pdf.h1("6. Compliance Requirements")
    compliance_reqs = ["GDPR Compliance", "PCI-DSS Level 1 Certification", "SOX Audit Trail",
                       "Role-based Access Control", "Data Encryption at Rest and in Transit"]
    for req in compliance_reqs:
        _track(doc_id, req)
        pdf.h3(req)
        pdf.para(
            f"The {req} requirement is a mandatory architectural constraint. Implementation details "
            f"are documented in the Compliance and Regulatory Requirements document (EA-CMP-016)."
        )
        pdf.para(_filler(req, 4))

    _track(doc_id, "Achieve Full Regulatory Compliance")
    _track(doc_id, "No Public Cloud for PII Data (until 2026 review)")
    pdf.para(
        f"The overarching goal is to {_use(doc_id, 'Achieve Full Regulatory Compliance')}. "
        f"The constraint '{_use(doc_id, 'No Public Cloud for PII Data (until 2026 review)')}' "
        f"limits deployment options for systems handling personally identifiable information."
    )

    # ADR table
    pdf.h1("7. Security Architecture Decisions")
    adr_headers = ["ADR ID", "Decision", "Status", "Date"]
    adr_rows = [
        ["SEC-001", "Use HSM for all key mgmt", "Accepted", "2024-03"],
        ["SEC-002", "Enforce TLS 1.3 only", "Accepted", "2024-05"],
        ["SEC-003", "MFA for all internal users", "Accepted", "2024-07"],
        ["SEC-004", "Zero-trust network model", "Proposed", "2025-01"],
        ["SEC-005", "SIEM migration to cloud", "Under Review", "2025-03"],
    ]
    pdf.table(adr_headers, adr_rows, [20, 55, 35, pdf._w - 110])
    _section_prose(pdf, "security architecture decisions ADR")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 07: Integration Architecture =====

def gen_doc_07():
    doc_id = "doc_07"
    pdf = DocPDF("Integration Architecture",
                 "EA-INT-007", "P. Jansen, Integration Architect")
    pdf.title_page("APIs, ESB, message queues, and data flows", "2.8")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Enterprise Service Bus"),
        ("3", "API Gateway and REST APIs"),
        ("4", "Event-Driven Integration (Kafka)"),
        ("5", "Application Interface Catalog"),
        ("6", "Data Flow Diagrams"),
        ("7", "API Endpoint Reference"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the integration architecture that connects ArchiSurance's "
        "application components. It covers synchronous (REST API), asynchronous (event streaming), "
        "and batch integration patterns. The Application Portfolio (EA-APP-002) provides details "
        "on individual components; this document focuses on how they communicate."
    )
    pdf.para(_long_para("integration architecture", 6, 10))
    _section_prose(pdf, "integration architecture patterns")

    # ESB
    pdf.h1("2. Enterprise Service Bus")
    _track(doc_id, "Enterprise Service Bus")
    _track(doc_id, "Apache Kafka")
    _track(doc_id, "CRM System")
    _track(doc_id, "Billing System")
    _track(doc_id, "Policy Administration System")
    pdf.para(
        f"The {_use(doc_id, 'Enterprise Service Bus')} is the backbone of ArchiSurance's "
        f"integration layer. Built on {_use(doc_id, 'Apache Kafka')}, it connects the "
        f"{_use(doc_id, 'CRM System')}, {_use(doc_id, 'Billing System')}, and "
        f"{_use(doc_id, 'Policy Administration System')} through message-based communication. "
        f"The ESB handles message routing, transformation, and guaranteed delivery."
    )
    pdf.para(_long_para("enterprise service bus integration", 6, 10))
    _section_prose(pdf, "enterprise service bus messaging")

    # API Gateway
    pdf.h1("3. API Gateway and REST APIs")
    _track(doc_id, "API Gateway")
    _track(doc_id, "REST API Gateway")
    _track(doc_id, "Customer Self-Service Portal")
    _track(doc_id, "Mobile App Backend")
    _track(doc_id, "Broker Portal")
    _track(doc_id, "Redis")
    _track(doc_id, "Identity & Access Management")
    pdf.para(
        f"The {_use(doc_id, 'API Gateway')} (exposed as the {_use(doc_id, 'REST API Gateway')} "
        f"interface) manages all external API traffic. It serves the "
        f"{_use(doc_id, 'Customer Self-Service Portal')}, {_use(doc_id, 'Mobile App Backend')}, "
        f"and {_use(doc_id, 'Broker Portal')}. Rate limiting and caching are provided by "
        f"{_use(doc_id, 'Redis')}. Authentication is delegated to "
        f"{_use(doc_id, 'Identity & Access Management')}."
    )
    pdf.para(_long_para("API gateway management", 6, 10))

    # Kafka
    pdf.h1("4. Event-Driven Integration (Kafka)")
    _track(doc_id, "Batch Processing Engine")
    _track(doc_id, "Data Warehouse")
    _track(doc_id, "Notification Service")
    _track(doc_id, "Fraud Detection Engine")
    _track(doc_id, "Claims Management Platform")
    pdf.para(
        f"Event-driven integration is implemented through {_use(doc_id, 'Apache Kafka')} with "
        f"the following topic structure:"
    )
    pdf.code_block(textwrap.dedent("""\
        # Kafka Topic Registry (archisurance-prod)
        claims.registered       - New claim events (producer: Claims Platform)
        claims.assessed         - Assessment outcome (producer: Claims Platform)
        fraud.scored            - Fraud score results (producer: Fraud Engine)
        policy.issued           - New policy events (producer: PAS)
        policy.renewed          - Renewal events (producer: PAS)
        customer.onboarded      - New customer events (producer: CRM)
        payment.processed       - Payment confirmations (producer: Billing)
        notification.requested  - Notification triggers (consumer: Notification Svc)
        analytics.events        - All events for DWH (consumer: Batch Processing)"""))

    pdf.para(
        f"The {_use(doc_id, 'Batch Processing Engine')} consumes all topics and loads data "
        f"into the {_use(doc_id, 'Data Warehouse')}. The {_use(doc_id, 'Notification Service')} "
        f"subscribes to claim and policy events. The {_use(doc_id, 'Fraud Detection Engine')} "
        f"consumes claim events and produces fraud scores consumed by the "
        f"{_use(doc_id, 'Claims Management Platform')}."
    )
    pdf.para(_long_para("event driven Kafka integration", 6, 10))
    _section_prose(pdf, "event driven Kafka streaming")

    # Interfaces
    pdf.h1("5. Application Interface Catalog")
    for iface in ENTITIES["ApplicationInterface"]:
        _track(doc_id, iface)
        pdf.h3(iface)
        pdf.para(
            f"The {iface} provides external connectivity. All interfaces use TLS 1.3 and "
            f"require OAuth 2.0 tokens issued by the {_use(doc_id, 'Identity & Access Management')} platform."
        )
        pdf.para(_filler(iface, 3))

    # Data Flows
    pdf.h1("6. Data Flow Diagrams")
    for svc in ENTITIES["ApplicationService"]:
        _track(doc_id, svc)
    pdf.para(
        "The following application services define the data flow contracts:"
    )
    for svc in ENTITIES["ApplicationService"]:
        realized_by = [r[2].split(":")[1] for r in RELATIONSHIPS
                       if r[0] == f"ApplicationService:{svc}" and r[1] == "Realization"]
        for rb in realized_by:
            _track(doc_id, rb)
        pdf.bullet(
            f"{svc} -- realized by {', '.join(_name(rb) for rb in realized_by) if realized_by else 'TBD'}"
        )
    pdf.para(_long_para("data flow architecture", 5, 8))

    # API Reference code block
    pdf.h1("7. API Endpoint Reference")
    pdf.h3("Claims API - OpenAPI Excerpt")
    pdf.code_block(textwrap.dedent("""\
        openapi: 3.0.3
        info:
          title: ArchiSurance Claims API
          version: 2.4.1
        paths:
          /api/v2/claims:
            post:
              summary: Register a new claim (FNOL)
              operationId: registerClaim
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/ClaimRequest'
              responses:
                '201':
                  description: Claim registered
                '400':
                  description: Validation error
          /api/v2/claims/{claimId}:
            get:
              summary: Retrieve claim details
              parameters:
                - name: claimId
                  in: path
                  required: true
                  schema:
                    type: string
              responses:
                '200':
                  description: Claim details
                '404':
                  description: Claim not found"""))
    _section_prose(pdf, "API endpoint design REST conventions")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 08: Data Architecture & Governance =====

def gen_doc_08():
    doc_id = "doc_08"
    pdf = DocPDF("Data Architecture & Governance",
                 "EA-DAT-008", "L. Hendriks, Data Architect")
    pdf.title_page("Data objects, ownership, lineage, and governance", "2.0")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Data Object Catalog"),
        ("3", "Data Ownership and Stewardship"),
        ("4", "Data Lineage"),
        ("5", "Data Storage Architecture"),
        ("6", "Data Quality Framework"),
        ("7", "Data Governance Policies"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document defines the data architecture and governance framework for ArchiSurance. "
        "It catalogs all data objects, their ownership, lineage from source to consumption, "
        "and the governance policies that ensure data quality and compliance. The Application "
        "Portfolio (EA-APP-002) describes which systems access each data object. The Compliance "
        "and Regulatory Requirements document (EA-CMP-016) details the regulatory constraints "
        "affecting data handling."
    )
    pdf.para(_long_para("data architecture governance", 6, 10))
    _section_prose(pdf, "data architecture governance framework")

    # Data Object Catalog
    pdf.h1("2. Data Object Catalog")
    for dobj in ENTITIES["DataObject"]:
        _track(doc_id, dobj)
        pdf.h2(f"2.x {dobj}")
        accessed_by = [r[0].split(":")[1] for r in RELATIONSHIPS
                       if r[2] == f"DataObject:{dobj}" and r[1] == "Access"]
        for ab in accessed_by:
            _track(doc_id, ab)

        pdf.para(
            f"The {dobj} is a core data asset within the ArchiSurance data model. "
            f"It is accessed by: {', '.join(_name(ab) for ab in accessed_by) if accessed_by else 'multiple systems'}."
        )
        pdf.para(
            f"Classification: {'PII' if 'Customer' in dobj or 'Policy' in dobj else 'Internal'}. "
            f"Retention period: {'7 years' if 'Regulatory' in dobj or 'Audit' in dobj else '5 years'}. "
            f"Backup frequency: Daily incremental, weekly full."
        )
        pdf.para(_filler(dobj, 4))

    # Ownership
    pdf.h1("3. Data Ownership and Stewardship")
    _track(doc_id, "Data Steward")
    _track(doc_id, "Data Analytics Team")
    _track(doc_id, "Compliance Officer")
    pdf.para(
        f"The {_use(doc_id, 'Data Steward')} role is responsible for ensuring data quality "
        f"standards are met. The {_use(doc_id, 'Data Analytics Team')} manages the analytical "
        f"data pipeline, while the {_use(doc_id, 'Compliance Officer')} oversees regulatory "
        f"data requirements."
    )
    ownership_headers = ["Data Object", "Business Owner", "Data Steward", "Classification"]
    ownership_rows = [
        ["Policy Record", "Policy Admin", "L. Hendriks", "PII"],
        ["Claim Record", "Claims Dept.", "T. Mulder", "PII"],
        ["Customer Record", "Sales Division", "S. Visser", "PII"],
        ["Premium Calc Data", "Underwriting", "K. Bakker", "Internal"],
        ["Fraud Score Dataset", "Data Analytics", "R. de Jong", "Confidential"],
        ["Commission Ledger", "Finance Dept.", "M. de Vries", "Internal"],
        ["Audit Log", "IT Operations", "P. Jansen", "Internal"],
        ["Regulatory Sub.", "Legal & Compl.", "R. de Jong", "Regulatory"],
        ["Document Metadata", "Policy Admin", "L. Hendriks", "Internal"],
        ["Analytics Cube", "Data Analytics", "K. Bakker", "Internal"],
    ]
    pdf.table(ownership_headers, ownership_rows, [40, 30, 30, pdf._w - 100])

    # Data Lineage
    pdf.h1("4. Data Lineage")
    _track(doc_id, "CRM System")
    _track(doc_id, "Policy Administration System")
    _track(doc_id, "Claims Management Platform")
    _track(doc_id, "Enterprise Service Bus")
    _track(doc_id, "Data Warehouse")
    _track(doc_id, "Batch Processing Engine")
    _track(doc_id, "Reporting & Analytics Platform")
    pdf.para(
        f"Data flows from source systems ({_use(doc_id, 'CRM System')}, "
        f"{_use(doc_id, 'Policy Administration System')}, {_use(doc_id, 'Claims Management Platform')}) "
        f"through the {_use(doc_id, 'Enterprise Service Bus')} to the "
        f"{_use(doc_id, 'Data Warehouse')} via the {_use(doc_id, 'Batch Processing Engine')}. "
        f"The {_use(doc_id, 'Reporting & Analytics Platform')} consumes data from the warehouse "
        f"for dashboards and regulatory reports."
    )
    pdf.para(_long_para("data lineage traceability", 6, 10))
    _section_prose(pdf, "data lineage traceability")

    # Storage
    pdf.h1("5. Data Storage Architecture")
    _track(doc_id, "PostgreSQL 15")
    _track(doc_id, "Oracle Database 19c")
    _track(doc_id, "Microsoft SQL Server 2022")
    _track(doc_id, "Elasticsearch")
    _track(doc_id, "Redis")
    pdf.para(
        f"Operational data is stored in {_use(doc_id, 'PostgreSQL 15')} (primary OLTP) and "
        f"{_use(doc_id, 'Oracle Database 19c')} (legacy billing and DWH). The "
        f"{_use(doc_id, 'Reporting & Analytics Platform')} uses "
        f"{_use(doc_id, 'Microsoft SQL Server 2022')} for OLAP workloads. "
        f"{_use(doc_id, 'Elasticsearch')} indexes document metadata, and "
        f"{_use(doc_id, 'Redis')} provides caching for frequently accessed data."
    )

    # SQL schema code block
    pdf.h3("Claims Database Schema (PostgreSQL)")
    pdf.code_block(textwrap.dedent("""\
        CREATE TABLE claims (
            claim_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            policy_id       UUID NOT NULL REFERENCES policies(policy_id),
            customer_id     UUID NOT NULL REFERENCES customers(customer_id),
            claim_type      VARCHAR(50) NOT NULL,
            claim_status    VARCHAR(30) NOT NULL DEFAULT 'REGISTERED',
            amount_claimed  DECIMAL(12,2),
            amount_approved DECIMAL(12,2),
            fraud_score     DECIMAL(5,4),
            submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            assessed_at     TIMESTAMPTZ,
            settled_at      TIMESTAMPTZ,
            handler_id      UUID REFERENCES employees(employee_id),
            CONSTRAINT chk_status CHECK (claim_status IN
                ('REGISTERED','ASSESSING','APPROVED','REJECTED','FRAUD_REVIEW','SETTLED'))
        );

        CREATE INDEX idx_claims_policy ON claims(policy_id);
        CREATE INDEX idx_claims_customer ON claims(customer_id);
        CREATE INDEX idx_claims_status ON claims(claim_status);
        CREATE INDEX idx_claims_submitted ON claims(submitted_at);"""))

    pdf.para(_long_para("data storage architecture", 5, 8))

    # Quality Framework
    pdf.h1("6. Data Quality Framework")
    pdf.para(
        "ArchiSurance employs a data quality framework with automated checks running daily. "
        "Quality dimensions measured include: completeness, accuracy, consistency, timeliness, "
        "and uniqueness. Quality scores are published to the Analytics Dashboard weekly."
    )
    pdf.para(_long_para("data quality framework", 6, 10))

    # Governance
    pdf.h1("7. Data Governance Policies")
    _track(doc_id, "GDPR Compliance")
    _track(doc_id, "SOX Audit Trail")
    pdf.para(
        f"Data governance at ArchiSurance is driven by regulatory requirements including "
        f"{_use(doc_id, 'GDPR Compliance')} and {_use(doc_id, 'SOX Audit Trail')}. "
        f"The governance council meets monthly to review data quality metrics and policy exceptions."
    )
    pdf.para(_long_para("data governance policies", 6, 10))
    _section_prose(pdf, "data governance policies compliance")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 09: Cloud Migration Assessment =====

def gen_doc_09():
    doc_id = "doc_09"
    pdf = DocPDF("Cloud Migration Assessment",
                 "EA-CLD-009", "J. van den Berg, Enterprise Architect")
    pdf.title_page("Current state vs target state analysis", "1.5")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Migration Drivers"),
        ("3", "Current State Assessment"),
        ("4", "Target State Architecture"),
        ("5", "Application Migration Readiness"),
        ("6", "Risk Analysis"),
        ("7", "Migration Roadmap"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document assesses ArchiSurance's readiness for cloud migration and defines the "
        "target-state architecture. The migration is driven by the strategic goal to "
        f"{_use(doc_id, 'Migrate 100% Workloads to Cloud by 2027')}, championed by the "
        f"{_use(doc_id, 'CTO')} and the {_use(doc_id, 'Enterprise Architect')}."
    )
    _track(doc_id, "Migrate 100% Workloads to Cloud by 2027")
    _track(doc_id, "CTO")
    _track(doc_id, "Enterprise Architect")
    pdf.para(
        "The assessment follows the '6 Rs' framework: Rehost, Replatform, Refactor, "
        "Repurchase, Retire, Retain. Each application component is evaluated against these "
        "options. For infrastructure details, see the Infrastructure Design Document (EA-INFRA-003)."
    )
    pdf.para(_long_para("cloud migration assessment", 6, 10))
    _section_prose(pdf, "cloud migration assessment readiness")

    # Drivers
    pdf.h1("2. Migration Drivers")
    _track(doc_id, "Reduce IT Operational Costs by 25%")
    _track(doc_id, "Achieve 99.9% System Availability")
    _track(doc_id, "Budget Cap EUR 2M Annual")
    _track(doc_id, "No Public Cloud for PII Data (until 2026 review)")
    _track(doc_id, "Vendor Lock-in Avoidance")
    _track(doc_id, "Minimum 3 Availability Zones")
    _track(doc_id, "CFO")
    pdf.para(
        f"The primary drivers are: (1) {_use(doc_id, 'Reduce IT Operational Costs by 25%')} -- "
        f"championed by the {_use(doc_id, 'CFO')}, (2) {_use(doc_id, 'Achieve 99.9% System Availability')} -- "
        f"requiring {_use(doc_id, 'Minimum 3 Availability Zones')}, and (3) the "
        f"{_use(doc_id, 'Legacy Oracle DB Migration Deadline Q4 2026')} constraint."
    )
    _track(doc_id, "Legacy Oracle DB Migration Deadline Q4 2026")
    pdf.para(
        f"Constraints: The {_use(doc_id, 'Budget Cap EUR 2M Annual')} limits the pace of migration. "
        f"The constraint '{_use(doc_id, 'No Public Cloud for PII Data (until 2026 review)')}' "
        f"requires a hybrid approach for PII-handling systems. "
        f"'{_use(doc_id, 'Vendor Lock-in Avoidance')}' mandates the use of cloud-agnostic technologies."
    )
    pdf.para(_long_para("cloud migration drivers", 6, 10))
    _section_prose(pdf, "cloud migration cost drivers")

    # Current State
    pdf.h1("3. Current State Assessment")
    for node in ENTITIES["Node"]:
        _track(doc_id, node)
    for sw in ENTITIES["SystemSoftware"]:
        _track(doc_id, sw)
    pdf.para(
        f"The current infrastructure consists of {len(ENTITIES['Node'])} compute nodes and "
        f"{len(ENTITIES['SystemSoftware'])} system software components. Key systems include "
        f"{_use(doc_id, 'PostgreSQL 15')} as the primary database, "
        f"{_use(doc_id, 'Oracle Database 19c')} for legacy workloads, and "
        f"{_use(doc_id, 'Kubernetes')} for container orchestration."
    )
    pdf.para(_long_para("current state infrastructure", 6, 10))
    _section_prose(pdf, "current state infrastructure assessment")

    # Target State
    pdf.h1("4. Target State Architecture")
    pdf.para(
        "The target state leverages managed cloud services while maintaining the existing "
        "application architecture. Key changes include: migration of PostgreSQL to a managed "
        "database service, replacement of the on-premises Kubernetes cluster with managed K8s, "
        "and retirement of the Oracle database through data migration to PostgreSQL."
    )
    pdf.para(_long_para("target state cloud architecture", 6, 10))
    _section_prose(pdf, "target state cloud architecture design")

    # App readiness table
    pdf.h1("5. Application Migration Readiness")
    headers = ["Application", "Strategy", "Effort", "PII?", "Priority"]
    rows = []
    strategies = ["Replatform", "Refactor", "Rehost", "Retain", "Repurchase"]
    efforts = ["Low", "Medium", "High"]
    for i, app in enumerate(ENTITIES["ApplicationComponent"]):
        _track(doc_id, app)
        rows.append([
            app[:22],
            strategies[i % len(strategies)],
            efforts[i % len(efforts)],
            "Yes" if i < 8 else "No",
            f"P{(i % 3) + 1}"
        ])
    pdf.table(headers, rows, [50, 28, 20, 15, pdf._w - 113])

    # Risk
    pdf.h1("6. Risk Analysis")
    pdf.para(
        "Key migration risks include data loss during cutover, performance degradation in "
        "shared cloud environments, regulatory non-compliance during transition, and skill "
        "gaps in the operations team. Mitigation strategies are defined in the Disaster "
        "Recovery Plan (EA-DR-010)."
    )
    pdf.para(_long_para("cloud migration risk analysis", 6, 10))

    # Roadmap
    pdf.h1("7. Migration Roadmap")
    roadmap_headers = ["Phase", "Period", "Workloads", "Milestone"]
    roadmap_rows = [
        ["Phase 1", "Q1-Q2 2025", "Dev/Test environments", "Cloud landing zone ready"],
        ["Phase 2", "Q3-Q4 2025", "Non-PII applications", "5 apps migrated"],
        ["Phase 3", "Q1-Q2 2026", "PII apps (post review)", "PII cloud approval"],
        ["Phase 4", "Q3-Q4 2026", "Oracle DB migration", "Oracle decommissioned"],
        ["Phase 5", "Q1-Q2 2027", "Remaining workloads", "DC exit complete"],
    ]
    pdf.table(roadmap_headers, roadmap_rows, [20, 28, 45, pdf._w - 93])
    _section_prose(pdf, "cloud migration roadmap planning")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 10: Disaster Recovery & Business Continuity =====

def gen_doc_10():
    doc_id = "doc_10"
    pdf = DocPDF("Disaster Recovery & Business Continuity Plan",
                 "EA-DR-010", "K. Bakker, Infrastructure Architect")
    pdf.title_page("RPO/RTO targets, failover procedures, and recovery plans", "3.0")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "RPO and RTO Targets"),
        ("3", "Failover Architecture"),
        ("4", "Database Recovery"),
        ("5", "Application Recovery Procedures"),
        ("6", "Network Recovery"),
        ("7", "Testing Schedule"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document defines the disaster recovery (DR) and business continuity plan (BCP) "
        "for ArchiSurance. It covers recovery objectives, failover architecture, and tested "
        "recovery procedures. The plan is aligned with the strategic goal to "
        f"{_use(doc_id, 'Achieve 99.9% System Availability')} and the requirements for "
        f"{_use(doc_id, 'RPO of 15 minutes')} and {_use(doc_id, 'RTO of 1 hour')}."
    )
    _track(doc_id, "Achieve 99.9% System Availability")
    _track(doc_id, "RPO of 15 minutes")
    _track(doc_id, "RTO of 1 hour")
    pdf.para(
        "For the infrastructure topology, refer to the Infrastructure Design Document "
        "(EA-INFRA-003). The Cloud Migration Assessment (EA-CLD-009) describes the evolving "
        "target state that will change DR procedures."
    )
    pdf.para(_long_para("disaster recovery business continuity", 6, 10))
    _section_prose(pdf, "disaster recovery planning")

    # RPO/RTO
    pdf.h1("2. RPO and RTO Targets")
    rpo_headers = ["System Tier", "RPO", "RTO", "DR Strategy"]
    rpo_rows = [
        ["Tier 1 (Critical)", "15 min", "1 hour", "Active-Passive failover"],
        ["Tier 2 (Important)", "1 hour", "4 hours", "Warm standby"],
        ["Tier 3 (Standard)", "24 hours", "24 hours", "Backup & restore"],
    ]
    pdf.table(rpo_headers, rpo_rows, [35, 20, 20, pdf._w - 75])
    pdf.para(
        f"Tier 1 systems include: {_use(doc_id, 'Claims Management Platform')}, "
        f"{_use(doc_id, 'Policy Administration System')}, {_use(doc_id, 'CRM System')}, "
        f"and the {_use(doc_id, 'Risk Engine')}."
    )
    for app in ["Claims Management Platform", "Policy Administration System", "CRM System", "Risk Engine"]:
        _track(doc_id, app)
    pdf.para(_long_para("RPO RTO targets", 5, 8))

    # Failover
    pdf.h1("3. Failover Architecture")
    _track(doc_id, "DR Recovery Node")
    _track(doc_id, "Database Server Replica")
    _track(doc_id, "Database Server Primary")
    _track(doc_id, "App Server Cluster")
    _track(doc_id, "Load Balancer F5")
    _track(doc_id, "Cloud VPN")
    pdf.para(
        f"The failover architecture uses the {_use(doc_id, 'DR Recovery Node')} in the "
        f"secondary data center (AMS-DC2) as the recovery target. The "
        f"{_use(doc_id, 'Database Server Replica')} maintains a synchronous copy of the "
        f"{_use(doc_id, 'Database Server Primary')}. In a failover event, the "
        f"{_use(doc_id, 'Load Balancer F5')} redirects traffic to the recovery cluster "
        f"via the {_use(doc_id, 'Cloud VPN')}."
    )
    pdf.para(_long_para("failover architecture", 6, 10))
    _section_prose(pdf, "failover architecture active passive")

    # DB Recovery
    pdf.h1("4. Database Recovery")
    _track(doc_id, "PostgreSQL 15")
    _track(doc_id, "Oracle Database 19c")
    _track(doc_id, "SAN Storage Array")
    _track(doc_id, "Backup Tape Library")
    pdf.para(
        f"Database recovery procedures differ by engine. {_use(doc_id, 'PostgreSQL 15')} uses "
        f"streaming replication with a hot standby on the {_use(doc_id, 'Database Server Replica')}. "
        f"{_use(doc_id, 'Oracle Database 19c')} uses Data Guard for log shipping. Both databases "
        f"are backed up to the {_use(doc_id, 'SAN Storage Array')} with offsite copies on the "
        f"{_use(doc_id, 'Backup Tape Library')}."
    )
    pdf.para(_long_para("database recovery procedures", 6, 10))
    _section_prose(pdf, "database recovery replication")

    # App Recovery
    pdf.h1("5. Application Recovery Procedures")
    _track(doc_id, "Kubernetes")
    _track(doc_id, "Docker Engine")
    _track(doc_id, "Notification Service")
    _track(doc_id, "Billing System")
    pdf.para(
        f"Container-based applications running on {_use(doc_id, 'Kubernetes')} and "
        f"{_use(doc_id, 'Docker Engine')} can be redeployed from container registries "
        f"within minutes. Stateful components like the {_use(doc_id, 'Billing System')} "
        f"require database recovery before application startup. The "
        f"{_use(doc_id, 'Notification Service')} has a built-in retry queue for messages "
        f"that could not be delivered during the outage."
    )
    pdf.para(_long_para("application recovery procedures", 6, 10))

    # Network Recovery
    pdf.h1("6. Network Recovery")
    _track(doc_id, "Corporate LAN")
    _track(doc_id, "DMZ Network")
    _track(doc_id, "Firewall Palo Alto")
    _track(doc_id, "WAN Accelerator")
    pdf.para(
        f"Network recovery involves re-establishing connectivity between the "
        f"{_use(doc_id, 'Corporate LAN')} and the {_use(doc_id, 'DMZ Network')} at the "
        f"secondary site. The {_use(doc_id, 'Firewall Palo Alto')} configuration is replicated "
        f"to the standby appliance. The {_use(doc_id, 'WAN Accelerator')} optimizes traffic "
        f"during the recovery period."
    )
    pdf.para(_long_para("network recovery failover", 6, 10))
    _section_prose(pdf, "network recovery failover procedures")

    # Testing
    pdf.h1("7. Testing Schedule")
    test_headers = ["Test Type", "Frequency", "Last Test", "Next Scheduled"]
    test_rows = [
        ["Tabletop Exercise", "Quarterly", "2025-01-15", "2025-04-15"],
        ["DB Failover Test", "Monthly", "2025-03-01", "2025-04-01"],
        ["Full DR Drill", "Annually", "2024-10-20", "2025-10-20"],
        ["Network Failover", "Semi-annual", "2024-12-05", "2025-06-05"],
        ["App Restore Test", "Monthly", "2025-03-10", "2025-04-10"],
    ]
    pdf.table(test_headers, test_rows, [35, 25, 25, pdf._w - 85])
    _section_prose(pdf, "DR testing schedule procedures")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 11: Network Architecture =====

def gen_doc_11():
    doc_id = "doc_11"
    pdf = DocPDF("Network Architecture",
                 "EA-NET-011", "K. Bakker, Network Architect")
    pdf.title_page("VLANs, firewalls, DMZ, and WAN design", "2.2")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Network Segmentation"),
        ("3", "Firewall Rules"),
        ("4", "Network Devices"),
        ("5", "IP Addressing Scheme"),
        ("6", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the network architecture of ArchiSurance, including network "
        "segmentation, firewall policies, device inventory, and IP addressing. The Security "
        "Architecture (EA-SEC-006) covers the security aspects of the network, and the "
        "Infrastructure Design Document (EA-INFRA-003) provides the compute layer context."
    )
    pdf.para(_long_para("network architecture design", 6, 10))
    _section_prose(pdf, "network architecture design")

    # Segmentation
    pdf.h1("2. Network Segmentation")
    for net in ENTITIES["CommunicationNetwork"]:
        _track(doc_id, net)
        pdf.h2(f"{_use(doc_id, net)}")
        devices_in = [r[0].split(":")[1] for r in RELATIONSHIPS
                      if r[2] == f"CommunicationNetwork:{net}" and r[1] == "Assignment"]
        for d in devices_in:
            _track(doc_id, d)
        pdf.para(
            f"The {_name(net)} segment provides connectivity for its assigned devices and nodes. "
            f"Connected devices: {', '.join(_name(d) for d in devices_in) if devices_in else 'various endpoints'}."
        )
        pdf.para(_long_para(net, 6, 10))

    # Firewall Rules
    pdf.h1("3. Firewall Rules")
    _track(doc_id, "Firewall Palo Alto")
    _track(doc_id, "Load Balancer F5")
    _track(doc_id, "API Gateway")
    pdf.para(
        f"The {_use(doc_id, 'Firewall Palo Alto')} enforces traffic policies between all "
        f"network segments. The following table summarizes key rules:"
    )
    fw_headers = ["Source", "Destination", "Port", "Action"]
    fw_rows = [
        ["Internet", "DMZ (LB F5)", "443", "Allow"],
        ["DMZ", "App Cluster", "8080", "Allow"],
        ["App Cluster", "DB Primary", "5432", "Allow"],
        ["App Cluster", "DB Primary", "1521", "Allow"],
        ["Mgmt VLAN", "All Nodes", "22", "Allow"],
        ["Corporate LAN", "Internet", "443,80", "Allow"],
        ["Any", "Any", "Any", "Deny"],
    ]
    pdf.table(fw_headers, fw_rows, [35, 35, 20, pdf._w - 90])
    pdf.para(_long_para("firewall rules policies", 5, 8))
    _section_prose(pdf, "firewall policies rules management")

    # Devices
    pdf.h1("4. Network Devices")
    for dev in ENTITIES["Device"]:
        _track(doc_id, dev)
        pdf.h3(_use(doc_id, dev))
        connects = [r[2].split(":")[1] for r in RELATIONSHIPS
                    if r[0] == f"Device:{dev}" and r[1] in ("Assignment", "Serving")]
        for c in connects:
            _track(doc_id, c)
        if connects:
            pdf.para(f"Connects to: {', '.join(_name(c) for c in connects)}.")
        pdf.para(_filler(dev, 4))

    # IP Addressing
    pdf.h1("5. IP Addressing Scheme")
    ip_headers = ["Segment", "Subnet", "Gateway", "VLAN ID"]
    ip_rows = [
        ["Corporate LAN", "10.10.0.0/16", "10.10.0.1", "100"],
        ["DMZ Network", "10.20.0.0/24", "10.20.0.1", "200"],
        ["Management VLAN", "10.30.0.0/24", "10.30.0.1", "300"],
        ["Cloud VPN", "172.16.0.0/16", "172.16.0.1", "N/A"],
        ["Database Subnet", "10.10.10.0/24", "10.10.10.1", "110"],
        ["App Cluster Subnet", "10.10.20.0/24", "10.10.20.1", "120"],
    ]
    pdf.table(ip_headers, ip_rows, [35, 35, 30, pdf._w - 100])
    _section_prose(pdf, "IP addressing subnet management")

    pdf.add_page()
    pdf.h1("6. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 12: Strategic IT Roadmap 2025-2027 =====

def gen_doc_12():
    doc_id = "doc_12"
    pdf = DocPDF("Strategic IT Roadmap 2025-2027",
                 "EA-ROAD-012", "Enterprise Architecture Team")
    pdf.title_page("Goals, capabilities, and transformation timeline", "2.0")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Strategic Goals"),
        ("3", "Capability Development Plan"),
        ("4", "Stakeholder Alignment"),
        ("5", "Requirements and Constraints"),
        ("6", "Timeline and Milestones"),
        ("7", "Investment Portfolio"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document presents ArchiSurance's Strategic IT Roadmap for the 2025-2027 planning "
        "horizon. It translates strategic goals into actionable capability development plans "
        "with clear timelines and investment requirements. The Enterprise Architecture Overview "
        "(EA-OVR-001) provides the architectural context, while the Cloud Migration Assessment "
        "(EA-CLD-009) details one of the major workstreams."
    )
    pdf.para(_long_para("strategic IT roadmap planning", 6, 10))
    _section_prose(pdf, "strategic IT roadmap planning")

    # Goals
    pdf.h1("2. Strategic Goals")
    for goal in ENTITIES["Goal"]:
        _track(doc_id, goal)
        pdf.h2(f"{_use(doc_id, goal)}")
        stakeholders = [r[0].split(":")[1] for r in RELATIONSHIPS
                        if r[2] == f"Goal:{goal}" and r[1] == "Association"]
        for s in stakeholders:
            _track(doc_id, s)
        influences = [r[2].split(":")[1] for r in RELATIONSHIPS
                      if r[0] == f"Goal:{goal}" and r[1] == "Influence"]
        for inf in influences:
            _track(doc_id, inf)
        pdf.para(
            f"Championed by: {', '.join(stakeholders) if stakeholders else 'leadership team'}."
        )
        if influences:
            pdf.para(f"Drives requirements: {', '.join(_name(inf) for inf in influences)}.")
        pdf.para(_long_para(goal, 5, 8))

    # Capabilities
    pdf.h1("3. Capability Development Plan")
    for cap in ENTITIES["Capability"]:
        _track(doc_id, cap)
        pdf.h3(_use(doc_id, cap))
        realizes = [r[2].split(":")[1] for r in RELATIONSHIPS
                    if r[0] == f"Capability:{cap}" and r[1] == "Realization"]
        for rl in realizes:
            _track(doc_id, rl)
        if realizes:
            pdf.para(f"Realizes: {', '.join(_name(rl) for rl in realizes)}.")
        pdf.para(_filler(cap, 4))

    # Stakeholders
    pdf.h1("4. Stakeholder Alignment")
    for sh in ENTITIES["Stakeholder"]:
        _track(doc_id, sh)
        goals = [r[2].split(":")[1] for r in RELATIONSHIPS
                 if r[0] == f"Stakeholder:{sh}" and r[1] == "Association"]
        for g in goals:
            _track(doc_id, g)
        pdf.h3(sh)
        pdf.para(
            f"Associated goals: {', '.join(_name(g) for g in goals) if goals else 'overall architecture direction'}."
        )
        pdf.para(_filler(sh, 3))

    # Requirements
    pdf.h1("5. Requirements and Constraints")
    for req in ENTITIES["Requirement"]:
        _track(doc_id, req)
        pdf.bullet(f"{_use(doc_id, req)}")
    pdf.ln(4)
    for con in ENTITIES["Constraint"]:
        _track(doc_id, con)
        pdf.bullet(f"{_use(doc_id, con)} (constraint)")
    pdf.para(_long_para("architectural requirements constraints", 5, 8))
    _section_prose(pdf, "architectural requirements constraints analysis")

    # Timeline
    pdf.h1("6. Timeline and Milestones")
    timeline_headers = ["Milestone", "Target Date", "Owner", "Status"]
    timeline_rows = [
        ["Cloud landing zone", "Q1 2025", "Infra Team", "Complete"],
        ["5 apps cloud-migrated", "Q4 2025", "Platform Eng", "In Progress"],
        ["Oracle decommission", "Q4 2026", "Data Team", "Planned"],
        ["Zero-trust network", "Q2 2026", "Security", "Planned"],
        ["100% cloud", "Q2 2027", "EA Team", "Planned"],
        ["Fraud ML v3 rollout", "Q3 2025", "Data Analytics", "In Progress"],
        ["Claims STP > 60%", "Q4 2025", "Claims IT", "In Progress"],
    ]
    pdf.table(timeline_headers, timeline_rows, [40, 22, 30, pdf._w - 92])

    # Investment
    pdf.h1("7. Investment Portfolio")
    inv_headers = ["Initiative", "2025 (kEUR)", "2026 (kEUR)", "2027 (kEUR)"]
    inv_rows = [
        ["Cloud Migration", "800", "600", "300"],
        ["Security Hardening", "300", "250", "200"],
        ["Claims Automation", "400", "300", "150"],
        ["Data Platform", "250", "200", "150"],
        ["Integration Modernization", "150", "150", "100"],
        ["Total", "1,900", "1,500", "900"],
    ]
    pdf.table(inv_headers, inv_rows, [45, 25, 25, pdf._w - 95])
    _section_prose(pdf, "IT investment portfolio budget")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 13: Service Catalog =====

def gen_doc_13():
    doc_id = "doc_13"
    pdf = DocPDF("IT Service Catalog",
                 "EA-SVC-013", "IT Operations Team")
    pdf.title_page("IT services with SLAs and support levels", "3.5")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Business Services"),
        ("3", "Technology Services"),
        ("4", "SLA Matrix"),
        ("5", "Support Model"),
        ("6", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This Service Catalog provides a comprehensive listing of all IT services offered "
        "to ArchiSurance business units. Each service is described with its SLA commitments, "
        "support model, and dependencies. The Strategic IT Roadmap (EA-ROAD-012) outlines "
        "future service enhancements."
    )
    pdf.para(_long_para("IT service catalog management", 6, 10))
    _section_prose(pdf, "IT service catalog management")

    # Business Services
    pdf.h1("2. Business Services")
    for svc in ENTITIES["BusinessService"]:
        _track(doc_id, svc)
        pdf.h2(svc)
        serves = [r[2].split(":")[1] for r in RELATIONSHIPS
                  if r[0] == f"BusinessService:{svc}" and r[1] == "Serving"]
        for s in serves:
            _track(doc_id, s)
        pdf.para(
            f"The {svc} is a business-facing IT service. "
            f"Supported processes: {', '.join(_name(s) for s in serves) if serves else 'various processes'}."
        )
        pdf.para(_filler(svc, 4))

    # Technology Services
    pdf.h1("3. Technology Services")
    for tsvc in ENTITIES["TechnologyService"]:
        _track(doc_id, tsvc)
        pdf.h3(tsvc)
        realized_by = [r[2].split(":")[1] for r in RELATIONSHIPS
                       if r[0] == f"TechnologyService:{tsvc}" and r[1] == "Realization"]
        for rb in realized_by:
            _track(doc_id, rb)
        pdf.para(
            f"Realized by: {', '.join(_name(rb) for rb in realized_by) if realized_by else 'infrastructure components'}."
        )
        pdf.para(_filler(tsvc, 3))

    # SLA Matrix
    pdf.h1("4. SLA Matrix")
    _track(doc_id, "SLA Premium Support")
    _track(doc_id, "Cloud Hosting SLA")
    _track(doc_id, "IT Service Manager")
    _track(doc_id, "SLA Monitoring")
    sla_headers = ["Service", "Availability", "Response Time", "Support Hours"]
    sla_rows = [
        ["Claims Handling Svc", "99.9%", "< 200ms", "24x7"],
        ["Insurance Policy Svc", "99.9%", "< 300ms", "24x7"],
        ["Customer Portal Svc", "99.5%", "< 500ms", "24x7"],
        ["Underwriting Svc", "99.5%", "< 1s", "Business hours"],
        ["Fraud Investigation", "99.0%", "< 2s", "Business hours"],
        ["Database Service", "99.99%", "N/A", "24x7"],
        ["Container Orch.", "99.9%", "N/A", "24x7"],
        ["Message Queue Svc", "99.9%", "N/A", "24x7"],
    ]
    pdf.table(sla_headers, sla_rows, [40, 25, 30, pdf._w - 95])
    pdf.para(
        f"SLA governance is defined in the {_use(doc_id, 'SLA Premium Support')} contract. "
        f"The {_use(doc_id, 'IT Service Manager')} role monitors compliance through the "
        f"{_use(doc_id, 'SLA Monitoring')} process."
    )
    pdf.para(_long_para("SLA management", 5, 8))
    _section_prose(pdf, "SLA management governance")

    # Support Model
    pdf.h1("5. Support Model")
    _track(doc_id, "IT Operations")
    _track(doc_id, "Reporting & Analytics Platform")
    pdf.para(
        f"Level 1 support is provided by the {_use(doc_id, 'IT Operations')} team during "
        f"business hours. Level 2 support is provided by application-specific teams. Level 3 "
        f"escalation involves vendor support. Incident metrics are tracked in the "
        f"{_use(doc_id, 'Reporting & Analytics Platform')}."
    )
    pdf.para(_long_para("IT support model", 6, 10))
    _section_prose(pdf, "IT support model tiered")

    # Contracts
    pdf.h1("5.1 Service Contracts")
    for contract in ENTITIES["Contract"]:
        _track(doc_id, contract)
        pdf.h3(contract)
        pdf.para(
            f"The {contract} governs the operational commitments for the associated services. "
            f"Contract review is conducted annually by the procurement team."
        )
        pdf.para(_filler(contract, 6))
    _section_prose(pdf, "service contracts procurement")

    pdf.add_page()
    pdf.h1("6. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 14: Vendor & Technology Assessment =====

def gen_doc_14():
    doc_id = "doc_14"
    pdf = DocPDF("Vendor & Technology Assessment",
                 "EA-VND-014", "P. Jansen, Technology Architect")
    pdf.title_page("Oracle, SAP, AWS, and open-source evaluation", "1.8")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Database Technology Assessment"),
        ("3", "Container Platform Assessment"),
        ("4", "Integration Technology Assessment"),
        ("5", "Vendor Risk Analysis"),
        ("6", "Recommendations"),
        ("7", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document assesses the technology vendors and platforms used by ArchiSurance, "
        "with a focus on strategic alignment, total cost of ownership, and risk. It informs "
        "the Cloud Migration Assessment (EA-CLD-009) and the Strategic IT Roadmap (EA-ROAD-012)."
    )
    pdf.para(_long_para("vendor technology assessment", 6, 10))
    _section_prose(pdf, "vendor technology assessment evaluation")

    # Database
    pdf.h1("2. Database Technology Assessment")
    for db in ["PostgreSQL 15", "Oracle Database 19c", "Microsoft SQL Server 2022"]:
        _track(doc_id, db)
        pdf.h2(_use(doc_id, db))
        serves = [r[2].split(":")[1] for r in RELATIONSHIPS
                  if r[0] == f"SystemSoftware:{db}" and r[1] == "Serving"]
        for s in serves:
            _track(doc_id, s)
        pdf.para(f"Serves: {', '.join(_name(s) for s in serves) if serves else 'various workloads'}.")
        pdf.para(_long_para(db, 6, 10))

    # Container Platform
    pdf.h1("3. Container Platform Assessment")
    for tech in ["Kubernetes", "Docker Engine"]:
        _track(doc_id, tech)
        pdf.h2(_use(doc_id, tech))
        assigns = [r[2].split(":")[1] for r in RELATIONSHIPS
                   if r[0] == f"SystemSoftware:{tech}" and r[1] == "Assignment"]
        for a in assigns:
            _track(doc_id, a)
        pdf.para(f"Hosts: {', '.join(_name(a) for a in assigns) if assigns else 'various apps'}.")
        pdf.para(_long_para(tech, 6, 10))

    # Integration
    pdf.h1("4. Integration Technology Assessment")
    for tech in ["Apache Kafka", "Redis", "Elasticsearch", "Nginx"]:
        _track(doc_id, tech)
        pdf.h3(_use(doc_id, tech))
        serves = [r[2].split(":")[1] for r in RELATIONSHIPS
                  if r[0] == f"SystemSoftware:{tech}" and r[1] in ("Serving", "Assignment")]
        for s in serves:
            _track(doc_id, s)
        pdf.para(f"Supports: {', '.join(_name(s) for s in serves) if serves else 'infrastructure'}.")
        pdf.para(_filler(tech, 4))

    # Vendor Risk
    pdf.h1("5. Vendor Risk Analysis")
    _track(doc_id, "Vendor Lock-in Avoidance")
    _track(doc_id, "Third-Party Data Provider Contract")
    _track(doc_id, "Legacy Oracle DB Migration Deadline Q4 2026")
    pdf.para(
        f"The constraint '{_use(doc_id, 'Vendor Lock-in Avoidance')}' drives the preference "
        f"for open-source and cloud-agnostic technologies. The "
        f"{_use(doc_id, 'Third-Party Data Provider Contract')} introduces a dependency on "
        f"external data quality. The {_use(doc_id, 'Legacy Oracle DB Migration Deadline Q4 2026')} "
        f"creates urgency for the database migration."
    )
    risk_headers = ["Vendor/Tech", "Risk Level", "Lock-in", "Alternative"]
    risk_rows = [
        ["Oracle DB 19c", "High", "High", "PostgreSQL 15"],
        ["Kubernetes", "Low", "Low", "Nomad / ECS"],
        ["Apache Kafka", "Medium", "Medium", "RabbitMQ / Pulsar"],
        ["Elasticsearch", "Medium", "Medium", "OpenSearch"],
        ["Redis", "Low", "Low", "Memcached / Valkey"],
        ["Nginx", "Low", "Low", "HAProxy / Envoy"],
    ]
    pdf.table(risk_headers, risk_rows, [35, 22, 22, pdf._w - 79])
    pdf.para(_long_para("vendor risk analysis", 6, 10))
    _section_prose(pdf, "vendor risk analysis lock-in")

    # Recommendations
    pdf.h1("6. Recommendations")
    pdf.para(
        "Based on the assessment, the Architecture Board recommends: (1) Accelerate Oracle "
        "to PostgreSQL migration, (2) Adopt managed Kubernetes in cloud, (3) Evaluate "
        "OpenSearch as Elasticsearch alternative, (4) Maintain Redis and Nginx as they "
        "present low vendor risk."
    )
    pdf.para(_long_para("technology vendor recommendations", 6, 10))
    _section_prose(pdf, "technology vendor recommendations")

    pdf.add_page()
    pdf.h1("7. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 15: Operational Runbook =====

def gen_doc_15():
    doc_id = "doc_15"
    pdf = DocPDF("Operational Runbook: Core Platform",
                 "EA-OPS-015", "IT Operations Team")
    pdf.title_page("Procedures, troubleshooting, and operational support", "4.1")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "On-Call Procedures"),
        ("3", "Kubernetes Operations"),
        ("4", "Database Operations"),
        ("5", "Kafka Operations"),
        ("6", "Monitoring and Alerting"),
        ("7", "Common Issues and Resolutions"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This Operational Runbook provides standard operating procedures for the ArchiSurance "
        "core platform. It is intended for the IT Operations team and on-call engineers. "
        "The Infrastructure Design Document (EA-INFRA-003) provides the architectural context, "
        "and the Disaster Recovery Plan (EA-DR-010) covers disaster scenarios."
    )
    pdf.para(_long_para("operational runbook procedures", 6, 10))
    _section_prose(pdf, "operational runbook procedures")

    # On-Call
    pdf.h1("2. On-Call Procedures")
    _track(doc_id, "IT Operations")
    _track(doc_id, "IT Service Manager")
    _track(doc_id, "SLA Monitoring")
    _track(doc_id, "Release Manager")
    pdf.para(
        f"The {_use(doc_id, 'IT Operations')} team maintains 24x7 on-call coverage. The "
        f"{_use(doc_id, 'IT Service Manager')} is the escalation point. The "
        f"{_use(doc_id, 'Release Manager')} must be notified before any production changes. "
        f"The {_use(doc_id, 'SLA Monitoring')} process generates alerts for SLA breaches."
    )
    pdf.para(_long_para("on-call procedures escalation", 6, 10))
    _section_prose(pdf, "on-call procedures escalation")

    # K8s Ops
    pdf.h1("3. Kubernetes Operations")
    _track(doc_id, "Kubernetes")
    _track(doc_id, "App Server Cluster")
    _track(doc_id, "Claims Management Platform")
    _track(doc_id, "Risk Engine")
    _track(doc_id, "Fraud Detection Engine")
    _track(doc_id, "API Gateway")
    _track(doc_id, "Notification Service")
    pdf.para(
        f"The {_use(doc_id, 'Kubernetes')} cluster runs on the {_use(doc_id, 'App Server Cluster')}. "
        f"Critical workloads: {_use(doc_id, 'Claims Management Platform')}, "
        f"{_use(doc_id, 'Risk Engine')}, {_use(doc_id, 'Fraud Detection Engine')}, "
        f"{_use(doc_id, 'API Gateway')}, {_use(doc_id, 'Notification Service')}."
    )
    pdf.h3("Scaling Procedure")
    pdf.code_block(textwrap.dedent("""\
        # Scale claims-service deployment
        kubectl -n archisurance-prod scale deployment claims-service --replicas=5

        # Check rollout status
        kubectl -n archisurance-prod rollout status deployment/claims-service

        # View pod logs
        kubectl -n archisurance-prod logs -l app=claims-service --tail=100

        # Emergency pod restart
        kubectl -n archisurance-prod rollout restart deployment/claims-service"""))
    pdf.para(_long_para("Kubernetes operations management", 6, 10))
    _section_prose(pdf, "Kubernetes cluster operations")

    # DB Ops
    pdf.h1("4. Database Operations")
    _track(doc_id, "PostgreSQL 15")
    _track(doc_id, "Oracle Database 19c")
    _track(doc_id, "Database Server Primary")
    _track(doc_id, "Database Server Replica")
    pdf.para(
        f"The {_use(doc_id, 'PostgreSQL 15')} cluster consists of the "
        f"{_use(doc_id, 'Database Server Primary')} and {_use(doc_id, 'Database Server Replica')}. "
        f"The {_use(doc_id, 'Oracle Database 19c')} runs on the same primary server."
    )
    pdf.h3("PostgreSQL Health Check")
    pdf.code_block(textwrap.dedent("""\
        -- Check replication status
        SELECT client_addr, state, sent_lsn, write_lsn, replay_lsn
        FROM pg_stat_replication;

        -- Check active connections
        SELECT datname, count(*) FROM pg_stat_activity
        WHERE state = 'active' GROUP BY datname;

        -- Check table bloat
        SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
        FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"""))
    pdf.para(_long_para("database operations maintenance", 6, 10))

    # Kafka Ops
    pdf.h1("5. Kafka Operations")
    _track(doc_id, "Apache Kafka")
    _track(doc_id, "Batch Processing Node")
    _track(doc_id, "Enterprise Service Bus")
    pdf.para(
        f"The {_use(doc_id, 'Apache Kafka')} cluster runs on the "
        f"{_use(doc_id, 'Batch Processing Node')}. It powers the "
        f"{_use(doc_id, 'Enterprise Service Bus')} and event streaming."
    )
    pdf.h3("Kafka Topic Management")
    pdf.code_block(textwrap.dedent("""\
        # List all topics
        kafka-topics.sh --bootstrap-server kafka-01:9092 --list

        # Check consumer lag
        kafka-consumer-groups.sh --bootstrap-server kafka-01:9092 \\
            --describe --group claims-processor-group

        # Reset consumer offset (CAUTION)
        kafka-consumer-groups.sh --bootstrap-server kafka-01:9092 \\
            --group claims-processor-group --topic claims.registered \\
            --reset-offsets --to-latest --execute"""))
    pdf.para(_long_para("Kafka operations management", 5, 8))

    # Monitoring
    pdf.h1("6. Monitoring and Alerting")
    _track(doc_id, "Elasticsearch")
    _track(doc_id, "Monitoring Server")
    _track(doc_id, "Log Aggregation Node")
    _track(doc_id, "Log Aggregation Service")
    pdf.para(
        f"Monitoring is provided by Prometheus and Grafana running on the "
        f"{_use(doc_id, 'Monitoring Server')}. Log aggregation uses the "
        f"{_use(doc_id, 'Elasticsearch')} cluster on the {_use(doc_id, 'Log Aggregation Node')}. "
        f"The {_use(doc_id, 'Log Aggregation Service')} collects logs from all application "
        f"and infrastructure components."
    )
    pdf.para(_long_para("monitoring alerting observability", 6, 10))
    _section_prose(pdf, "monitoring alerting observability")

    # Common Issues
    pdf.h1("7. Common Issues and Resolutions")
    issues = [
        ("High CPU on claims-service pods", "Scale horizontally. Check for stuck workflows in the Workflow Engine."),
        ("PostgreSQL replication lag > 30s", "Check network between DC1 and DC2. Consider WAL archiving backlog."),
        ("Kafka consumer lag increasing", "Check Batch Processing Engine health. May need to increase partition count."),
        ("API Gateway 502 errors", "Check upstream service health. Verify Redis cache connectivity."),
        ("Certificate expiry alert", "Renew via Certificate Management Service. Update HSM Appliance if needed."),
    ]
    for issue, resolution in issues:
        pdf.h3(f"Issue: {issue}")
        pdf.para(f"Resolution: {resolution}")
        pdf.para(_filler(issue, 5))
        pdf.ln(2)
    _section_prose(pdf, "common operational issues troubleshooting")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 16: Compliance & Regulatory Requirements =====

def gen_doc_16():
    doc_id = "doc_16"
    pdf = DocPDF("Compliance & Regulatory Requirements",
                 "EA-CMP-016", "R. de Jong, Compliance Manager")
    pdf.title_page("GDPR, PCI-DSS, SOX, and architectural constraints", "2.5")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "GDPR Compliance"),
        ("3", "PCI-DSS Level 1"),
        ("4", "SOX Audit Requirements"),
        ("5", "Architectural Constraints"),
        ("6", "Compliance Mapping to Architecture"),
        ("7", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the regulatory and compliance requirements that shape "
        "ArchiSurance's architecture. As a financial services organization, ArchiSurance "
        "is subject to GDPR, PCI-DSS, and SOX regulations. The Security Architecture "
        "(EA-SEC-006) details the technical controls, while this document focuses on "
        "requirements and their traceability to architectural decisions."
    )
    pdf.para(_long_para("compliance regulatory requirements", 6, 10))
    _section_prose(pdf, "compliance regulatory requirements")

    # GDPR
    pdf.h1("2. GDPR Compliance")
    _track(doc_id, "GDPR Compliance")
    _track(doc_id, "Achieve Full Regulatory Compliance")
    _track(doc_id, "Legal & Compliance")
    _track(doc_id, "Compliance Officer")
    _track(doc_id, "Customer Record")
    _track(doc_id, "Policy Record")
    _track(doc_id, "Identity & Access Management")
    pdf.para(
        f"The {_use(doc_id, 'GDPR Compliance')} requirement mandates that all processing of "
        f"personal data complies with the EU General Data Protection Regulation. The "
        f"{_use(doc_id, 'Legal & Compliance')} department, through the "
        f"{_use(doc_id, 'Compliance Officer')} role, oversees compliance."
    )
    pdf.para(
        f"Key data objects affected: {_use(doc_id, 'Customer Record')}, "
        f"{_use(doc_id, 'Policy Record')}. Access control is enforced through the "
        f"{_use(doc_id, 'Identity & Access Management')} platform."
    )
    pdf.para(_long_para("GDPR compliance data protection", 6, 10))
    _section_prose(pdf, "GDPR compliance data protection")

    # PCI-DSS
    pdf.h1("3. PCI-DSS Level 1")
    _track(doc_id, "PCI-DSS Level 1 Certification")
    _track(doc_id, "Billing System")
    _track(doc_id, "Data Encryption at Rest and in Transit")
    _track(doc_id, "Commission Ledger")
    _track(doc_id, "HSM Appliance")
    pdf.para(
        f"The {_use(doc_id, 'PCI-DSS Level 1 Certification')} requirement applies to all "
        f"systems that process payment card data. The {_use(doc_id, 'Billing System')} and "
        f"the {_use(doc_id, 'Commission Ledger')} are in scope. {_use(doc_id, 'Data Encryption at Rest and in Transit')} "
        f"is mandatory, with key management handled by the {_use(doc_id, 'HSM Appliance')}."
    )
    pdf.para(_long_para("PCI-DSS payment card security", 6, 10))
    _section_prose(pdf, "PCI-DSS payment card security")

    # SOX
    pdf.h1("4. SOX Audit Requirements")
    _track(doc_id, "SOX Audit Trail")
    _track(doc_id, "Audit Log")
    _track(doc_id, "Internal Audit")
    _track(doc_id, "Reporting & Analytics Platform")
    _track(doc_id, "Regulatory Submission Record")
    pdf.para(
        f"The {_use(doc_id, 'SOX Audit Trail')} requirement mandates that all financial "
        f"transactions are logged with immutable audit trails. The {_use(doc_id, 'Audit Log')} "
        f"data object captures these events. {_use(doc_id, 'Internal Audit')} reviews the "
        f"audit trails quarterly using the {_use(doc_id, 'Reporting & Analytics Platform')}."
    )
    pdf.para(
        f"Regulatory submissions are tracked in the {_use(doc_id, 'Regulatory Submission Record')} "
        f"and filed through the {_use(doc_id, 'Regulatory Filing Service')}."
    )
    _track(doc_id, "Regulatory Filing Service")
    pdf.para(_long_para("SOX audit requirements", 6, 10))
    _section_prose(pdf, "SOX audit requirements trail")

    # Constraints
    pdf.h1("5. Architectural Constraints")
    for con in ENTITIES["Constraint"]:
        _track(doc_id, con)
        pdf.h3(_use(doc_id, con))
        influences = [r[2].split(":")[1] for r in RELATIONSHIPS
                      if r[0] == f"Constraint:{con}" and r[1] == "Influence"]
        for inf in influences:
            _track(doc_id, inf)
        if influences:
            pdf.para(f"Influences: {', '.join(_name(inf) for inf in influences)}.")
        pdf.para(_filler(con, 4))

    _track(doc_id, "Role-based Access Control")
    _track(doc_id, "No Public Cloud for PII Data (until 2026 review)")
    pdf.para(
        f"Additionally, the {_use(doc_id, 'Role-based Access Control')} requirement and "
        f"the constraint '{_use(doc_id, 'No Public Cloud for PII Data (until 2026 review)')}' "
        f"directly affect deployment and access architecture decisions."
    )

    # Compliance mapping
    pdf.h1("6. Compliance Mapping to Architecture")
    comp_headers = ["Requirement", "Affected System", "Control", "Status"]
    comp_rows = [
        ["GDPR", "CRM System", "Data encryption, RBAC", "Compliant"],
        ["GDPR", "Policy Admin Sys", "Data encryption, RBAC", "Compliant"],
        ["PCI-DSS", "Billing System", "HSM key mgmt, TDE", "Compliant"],
        ["SOX", "Reporting Platform", "Immutable audit log", "In Progress"],
        ["SOX", "Billing System", "Transaction logging", "Compliant"],
        ["GDPR", "Data Warehouse", "Pseudonymization", "In Progress"],
    ]
    pdf.table(comp_headers, comp_rows, [25, 38, 42, pdf._w - 105])

    _track(doc_id, "CRM System")
    _track(doc_id, "Policy Administration System")
    _track(doc_id, "Data Warehouse")
    _section_prose(pdf, "compliance mapping architecture controls")

    pdf.add_page()
    pdf.h1("7. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_acronym_glossary()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===== Document 17: Change Management - ERP Migration =====

def gen_doc_17():
    doc_id = "doc_17"
    pdf = DocPDF("Change Management: ERP Migration",
                 "EA-CHG-017", "M. de Vries, Change Manager")
    pdf.title_page("Oracle to PostgreSQL migration -- impact analysis and rollback plan", "1.2")
    pdf.version_history()
    pdf.toc([
        ("1", "Introduction"),
        ("2", "Migration Scope"),
        ("3", "Impact Analysis"),
        ("4", "Data Migration Plan"),
        ("5", "Application Changes"),
        ("6", "Rollback Plan"),
        ("7", "Testing Strategy"),
        ("8", "Appendices"),
    ])

    pdf.add_page()
    pdf.h1("1. Introduction")
    pdf.para(
        "This document describes the change management plan for migrating from "
        f"{_use(doc_id, 'Oracle Database 19c')} to {_use(doc_id, 'PostgreSQL 15')} as the "
        f"primary database for billing and data warehousing workloads. The migration is driven "
        f"by the constraint '{_use(doc_id, 'Legacy Oracle DB Migration Deadline Q4 2026')}' and "
        f"the goal to {_use(doc_id, 'Reduce IT Operational Costs by 25%')}."
    )
    _track(doc_id, "Oracle Database 19c")
    _track(doc_id, "PostgreSQL 15")
    _track(doc_id, "Legacy Oracle DB Migration Deadline Q4 2026")
    _track(doc_id, "Reduce IT Operational Costs by 25%")
    pdf.para(
        "For the broader cloud migration context, see the Cloud Migration Assessment "
        "(EA-CLD-009). The Vendor and Technology Assessment (EA-VND-014) provides the "
        "technical rationale for the PostgreSQL choice."
    )
    pdf.para(_long_para("ERP migration change management", 6, 10))
    _section_prose(pdf, "ERP migration change management")

    # Scope
    pdf.h1("2. Migration Scope")
    _track(doc_id, "Billing System")
    _track(doc_id, "Data Warehouse")
    _track(doc_id, "Commission Ledger")
    _track(doc_id, "Analytics Cube")
    _track(doc_id, "Batch Processing Engine")
    _track(doc_id, "Reporting & Analytics Platform")
    pdf.para(
        f"The migration scope includes the following systems currently on Oracle: "
        f"{_use(doc_id, 'Billing System')} (accessing {_use(doc_id, 'Commission Ledger')}), "
        f"{_use(doc_id, 'Data Warehouse')} (storing {_use(doc_id, 'Analytics Cube')} data). "
        f"Downstream consumers include the {_use(doc_id, 'Batch Processing Engine')} and the "
        f"{_use(doc_id, 'Reporting & Analytics Platform')}."
    )
    pdf.para(_long_para("migration scope definition", 6, 10))
    _section_prose(pdf, "migration scope definition")

    # Impact Analysis
    pdf.h1("3. Impact Analysis")
    _track(doc_id, "Broker Commission Settlement")
    _track(doc_id, "Premium Calculation")
    _track(doc_id, "Finance Department")
    _track(doc_id, "Enterprise Service Bus")
    _track(doc_id, "Regulatory Reporting")
    pdf.para(
        f"The migration will impact the following business processes: "
        f"{_use(doc_id, 'Broker Commission Settlement')} (directly depends on "
        f"{_use(doc_id, 'Billing System')}), {_use(doc_id, 'Premium Calculation')} "
        f"(through billing integration), and {_use(doc_id, 'Regulatory Reporting')} "
        f"(through the {_use(doc_id, 'Data Warehouse')}). The {_use(doc_id, 'Finance Department')} "
        f"is the primary business stakeholder."
    )
    pdf.para(
        f"Integration impact: The {_use(doc_id, 'Enterprise Service Bus')} routes messages "
        f"to the billing system. Connection strings and message schemas may need updates. "
        f"The {_use(doc_id, 'Batch Processing Engine')} ETL pipelines require Oracle-to-PostgreSQL "
        f"SQL dialect conversion."
    )
    pdf.para(_long_para("impact analysis assessment", 6, 10))
    _section_prose(pdf, "impact analysis business process")

    # Data Migration Plan
    pdf.h1("4. Data Migration Plan")
    _track(doc_id, "Database Server Primary")
    _track(doc_id, "Database Server Replica")
    _track(doc_id, "SAN Storage Array")
    pdf.para(
        f"Data will be migrated from Oracle on the {_use(doc_id, 'Database Server Primary')} "
        f"to PostgreSQL on the same hardware (in-place migration). The "
        f"{_use(doc_id, 'Database Server Replica')} will serve as the PostgreSQL standby. "
        f"Full backups will be stored on the {_use(doc_id, 'SAN Storage Array')} before "
        f"migration begins."
    )
    pdf.h3("Migration SQL Example")
    pdf.code_block(textwrap.dedent("""\
        -- Oracle to PostgreSQL migration: Commission Ledger
        -- Step 1: Export from Oracle
        expdp system/*** schemas=BILLING dumpfile=billing_export.dmp

        -- Step 2: Convert schema using ora2pg
        ora2pg -t TABLE -o billing_tables.sql -s BILLING
        ora2pg -t INSERT -o billing_data.sql -s BILLING

        -- Step 3: Import into PostgreSQL
        psql -h ams-db-01 -U archisurance -d billing -f billing_tables.sql
        psql -h ams-db-01 -U archisurance -d billing -f billing_data.sql

        -- Step 4: Verify row counts
        SELECT 'policies' AS tbl, count(*) FROM policies
        UNION ALL
        SELECT 'commissions', count(*) FROM commissions
        UNION ALL
        SELECT 'invoices', count(*) FROM invoices;"""))
    pdf.para(_long_para("data migration planning", 6, 10))
    _section_prose(pdf, "data migration planning Oracle to PostgreSQL")

    # Application Changes
    pdf.h1("5. Application Changes")
    _track(doc_id, "Microsoft SQL Server 2022")
    _track(doc_id, "CRM System")
    _track(doc_id, "Policy Administration System")
    pdf.para(
        f"The {_use(doc_id, 'Billing System')} will require connection string changes and "
        f"Oracle-specific SQL conversion (e.g., ROWNUM to LIMIT/OFFSET, NVL to COALESCE). "
        f"The {_use(doc_id, 'Data Warehouse')} ETL stored procedures must be rewritten. "
        f"The {_use(doc_id, 'Reporting & Analytics Platform')} remains on "
        f"{_use(doc_id, 'Microsoft SQL Server 2022')} and is unaffected. "
        f"The {_use(doc_id, 'CRM System')} and {_use(doc_id, 'Policy Administration System')} "
        f"already use PostgreSQL and are unaffected."
    )
    pdf.para(_long_para("application changes migration", 6, 10))

    # Rollback Plan
    pdf.h1("6. Rollback Plan")
    _track(doc_id, "Backup Tape Library")
    _track(doc_id, "DR Recovery Node")
    pdf.para(
        f"In case of critical issues during migration, the rollback procedure is: "
        f"(1) Stop all application connections to the new PostgreSQL instance, "
        f"(2) Restore the Oracle database from the pre-migration backup on the "
        f"{_use(doc_id, 'SAN Storage Array')}, (3) Re-point application connection strings "
        f"to Oracle, (4) Verify data integrity through automated reconciliation scripts. "
        f"A full Oracle backup is also retained on the {_use(doc_id, 'Backup Tape Library')} "
        f"and the {_use(doc_id, 'DR Recovery Node')} for 90 days post-migration."
    )
    pdf.para(_long_para("rollback plan procedures", 6, 10))
    _section_prose(pdf, "rollback plan disaster recovery")

    # Testing
    pdf.h1("7. Testing Strategy")
    _track(doc_id, "CI/CD Build Server")
    pdf.para(
        f"The testing strategy uses the {_use(doc_id, 'CI/CD Build Server')} for automated "
        f"regression testing. Test phases include: (1) Schema comparison, (2) Row-level data "
        f"validation, (3) Application integration testing, (4) Performance benchmarking, "
        f"(5) User acceptance testing."
    )
    test_headers = ["Phase", "Duration", "Owner", "Go/No-Go"]
    test_rows = [
        ["Schema Validation", "1 week", "DBA Team", "Automated"],
        ["Data Reconciliation", "2 weeks", "Data Team", "Automated + Manual"],
        ["Integration Testing", "2 weeks", "App Teams", "Manual"],
        ["Performance Testing", "1 week", "Infra Team", "Automated"],
        ["UAT", "2 weeks", "Business Users", "Manual sign-off"],
    ]
    pdf.table(test_headers, test_rows, [35, 22, 30, pdf._w - 87])
    _section_prose(pdf, "migration testing strategy validation")

    pdf.add_page()
    pdf.h1("8. Appendices")
    pdf.noise_references()
    pdf.noise_distribution_list()
    pdf.noise_meeting_notes()
    pdf.noise_revision_notes()
    pdf.noise_disclaimer()

    return pdf, doc_id


# ===========================================================================
# Ground truth and eval questions generation
# ===========================================================================

def _build_ground_truth():
    """Build the ground truth JSON from the model."""
    # Per-doc entity presence
    doc_entity_presence = {}
    for doc_id, entities in _doc_entities.items():
        doc_entity_presence[doc_id] = sorted(entities)

    return {
        "entities": ENTITIES,
        "relationships": [
            {"source": r[0], "type": r[1], "target": r[2]}
            for r in RELATIONSHIPS
        ],
        "entity_counts": {k: len(v) for k, v in ENTITIES.items()},
        "relationship_count": len(RELATIONSHIPS),
        "total_entities": sum(len(v) for v in ENTITIES.values()),
        "document_entity_presence": doc_entity_presence,
    }


def _build_entity_aliases():
    """Build the alias mapping JSON."""
    return ENTITY_ALIASES


def _build_eval_questions():
    """Build 30 evaluation questions."""
    return [
        # ── Single-hop (8) ──
        {
            "id": "single_hop_1",
            "question": "Which business processes does the Claims Management Platform serve?",
            "expected_answer": "Claims Registration and Claims Assessment",
            "expected_entities": ["Claims Management Platform", "Claims Registration", "Claims Assessment"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
            "notes": "Direct Serving relationship"
        },
        {
            "id": "single_hop_2",
            "question": "What database system does the Policy Administration System use?",
            "expected_answer": "PostgreSQL 15",
            "expected_entities": ["Policy Administration System", "PostgreSQL 15"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
        },
        {
            "id": "single_hop_3",
            "question": "Who is responsible for Risk Evaluation?",
            "expected_answer": "The Underwriting Team is assigned to Risk Evaluation",
            "expected_entities": ["Underwriting Team", "Risk Evaluation"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
        },
        {
            "id": "single_hop_4",
            "question": "What data objects does the Fraud Detection Engine access?",
            "expected_answer": "Fraud Score Dataset",
            "expected_entities": ["Fraud Detection Engine", "Fraud Score Dataset"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
        },
        {
            "id": "single_hop_5",
            "question": "Which application component realizes the Payment API?",
            "expected_answer": "Billing System",
            "expected_entities": ["Payment API", "Billing System"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
        },
        {
            "id": "single_hop_6",
            "question": "What system software hosts the API Gateway?",
            "expected_answer": "Kubernetes",
            "expected_entities": ["API Gateway", "Kubernetes"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
        },
        {
            "id": "single_hop_7",
            "question": "Which stakeholder champions the goal 'Zero Data Breaches by 2026'?",
            "expected_answer": "CISO and Chief Risk Officer",
            "expected_entities": ["CISO", "Chief Risk Officer", "Zero Data Breaches by 2026"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
        },
        {
            "id": "single_hop_8",
            "question": "What does the Enterprise Service Bus serve?",
            "expected_answer": "CRM System, Billing System, and Policy Administration System",
            "expected_entities": ["Enterprise Service Bus", "CRM System", "Billing System", "Policy Administration System"],
            "hop_count": 1,
            "category": "single_hop",
            "requires_graph": False,
        },
        # ── Multi-hop (8) ──
        {
            "id": "multi_hop_1",
            "question": "If we decommission Kubernetes, which business processes would be affected?",
            "expected_answer": "Claims Registration, Claims Assessment (via Claims Management Platform), Risk Evaluation, Premium Calculation (via Risk Engine), Fraud Detection (via Fraud Detection Engine), Customer Onboarding and Complaint Handling (via API Gateway -> Customer Self-Service Portal)",
            "expected_entities": ["Kubernetes", "Claims Management Platform", "Risk Engine", "Fraud Detection Engine", "API Gateway", "Claims Registration", "Claims Assessment", "Risk Evaluation", "Premium Calculation", "Fraud Detection"],
            "hop_count": 2,
            "category": "multi_hop",
            "requires_graph": True,
            "notes": "Requires traversal: Kubernetes -[Assignment]-> Applications -[Serving]-> Processes"
        },
        {
            "id": "multi_hop_2",
            "question": "What data objects are accessed by applications that serve Claims Assessment?",
            "expected_answer": "Claim Record (via Claims Management Platform), Premium Calculation Data (via Risk Engine), Fraud Score Dataset (via Fraud Detection Engine indirectly)",
            "expected_entities": ["Claims Assessment", "Claims Management Platform", "Risk Engine", "Claim Record", "Premium Calculation Data"],
            "hop_count": 2,
            "category": "multi_hop",
            "requires_graph": True,
        },
        {
            "id": "multi_hop_3",
            "question": "Which stakeholders are affected if the Database Server Primary fails?",
            "expected_answer": "Head of Claims (via PostgreSQL -> Claims Platform -> Claims processes -> Claims Processing goal), CTO (via system availability goal), CFO (via Oracle -> Billing -> cost reduction goal)",
            "expected_entities": ["Database Server Primary", "PostgreSQL 15", "Oracle Database 19c", "Claims Management Platform", "Billing System", "Head of Claims", "CTO", "CFO"],
            "hop_count": 3,
            "category": "multi_hop",
            "requires_graph": True,
            "notes": "3-hop: DB Server -> DB Software -> Applications -> Processes -> Goals -> Stakeholders"
        },
        {
            "id": "multi_hop_4",
            "question": "Trace the dependency chain from the SAN Storage Array to business processes.",
            "expected_answer": "SAN Storage Array serves Database Server Primary and Replica, which host PostgreSQL 15 and Oracle Database 19c, which serve Claims Management Platform, Policy Administration System, CRM System, Billing System, and Data Warehouse, which serve Claims Registration, Claims Assessment, Policy Issuance, Customer Onboarding, Broker Commission Settlement, etc.",
            "expected_entities": ["SAN Storage Array", "Database Server Primary", "Database Server Replica", "PostgreSQL 15", "Oracle Database 19c"],
            "hop_count": 3,
            "category": "multi_hop",
            "requires_graph": True,
        },
        {
            "id": "multi_hop_5",
            "question": "What capabilities are realized by processes that the Risk Engine serves?",
            "expected_answer": "Risk Assessment Intelligence (via Risk Evaluation) and Data-Driven Underwriting (via Premium Calculation)",
            "expected_entities": ["Risk Engine", "Risk Evaluation", "Premium Calculation", "Risk Assessment Intelligence", "Data-Driven Underwriting"],
            "hop_count": 2,
            "category": "multi_hop",
            "requires_graph": True,
        },
        {
            "id": "multi_hop_6",
            "question": "If Apache Kafka goes down, which business services would be impacted?",
            "expected_answer": "Kafka serves the Enterprise Service Bus and Batch Processing Engine. ESB serves CRM System, Billing System, Policy Administration System. These serve multiple business processes linked to Insurance Policy Service, Claims Handling Service, Premium Collection Service, etc.",
            "expected_entities": ["Apache Kafka", "Enterprise Service Bus", "Batch Processing Engine", "CRM System", "Billing System", "Policy Administration System"],
            "hop_count": 3,
            "category": "multi_hop",
            "requires_graph": True,
        },
        {
            "id": "multi_hop_7",
            "question": "What infrastructure supports the Fraud Scoring API end-to-end?",
            "expected_answer": "Fraud Scoring API is realized by Fraud Detection Engine, which runs on Kubernetes, deployed on App Server Cluster, connected via Corporate LAN",
            "expected_entities": ["Fraud Scoring API", "Fraud Detection Engine", "Kubernetes", "App Server Cluster"],
            "hop_count": 3,
            "category": "multi_hop",
            "requires_graph": True,
        },
        {
            "id": "multi_hop_8",
            "question": "Which goals are impacted by the constraint 'Legacy Oracle DB Migration Deadline Q4 2026'?",
            "expected_answer": "The constraint influences 'Migrate 100% Workloads to Cloud by 2027', which is championed by the CTO and Enterprise Architect. The migration also connects to 'Reduce IT Operational Costs by 25%' championed by the CFO.",
            "expected_entities": ["Legacy Oracle DB Migration Deadline Q4 2026", "Migrate 100% Workloads to Cloud by 2027", "CTO", "Enterprise Architect", "CFO"],
            "hop_count": 2,
            "category": "multi_hop",
            "requires_graph": True,
        },
        # ── Cross-document (6) ──
        {
            "id": "cross_doc_1",
            "question": "How does the CRM System relate to the strategic goal of Customer Satisfaction?",
            "expected_answer": "CRM System serves Customer Onboarding process, which is realized by the Omnichannel Distribution capability, connected to the Digital Customer Experience capability which realizes the Customer Portal Service. The goal 'Increase Customer Satisfaction to NPS 60+' is championed by the Chief Risk Officer.",
            "expected_entities": ["CRM System", "Customer Onboarding", "Digital Customer Experience", "Increase Customer Satisfaction to NPS 60+"],
            "hop_count": 3,
            "category": "cross_document",
            "requires_graph": True,
            "notes": "Information spans docs 01 (overview), 04 (CRM), 12 (roadmap)"
        },
        {
            "id": "cross_doc_2",
            "question": "What infrastructure supports the Risk Scoring API?",
            "expected_answer": "Risk Scoring API is realized by Risk Engine, which runs on Kubernetes, deployed on App Server Cluster",
            "expected_entities": ["Risk Scoring API", "Risk Engine", "Kubernetes", "App Server Cluster"],
            "hop_count": 3,
            "category": "cross_document",
            "requires_graph": True,
            "notes": "Spans docs 02 (app portfolio), 03 (infrastructure), 07 (integration)"
        },
        {
            "id": "cross_doc_3",
            "question": "What is the full impact chain of the Oracle Database 19c migration on business processes?",
            "expected_answer": "Oracle Database 19c serves Billing System and Data Warehouse. Billing System serves Broker Commission Settlement and Premium Calculation. Data Warehouse serves Reporting & Analytics Platform which serves Regulatory Reporting and SLA Monitoring. Migration details are in the ERP Migration document.",
            "expected_entities": ["Oracle Database 19c", "Billing System", "Data Warehouse", "Broker Commission Settlement", "Premium Calculation", "Regulatory Reporting"],
            "hop_count": 3,
            "category": "cross_document",
            "requires_graph": True,
            "notes": "Spans docs 03 (infra), 05 (claims), 14 (vendor), 17 (migration)"
        },
        {
            "id": "cross_doc_4",
            "question": "Which documents describe the Fraud Detection Engine and its role?",
            "expected_answer": "The Application Portfolio (doc 02) catalogs it, the Claims Processing Workflow (doc 05) describes its role in claims fraud screening, the Integration Architecture (doc 07) shows its Kafka integration, and the Operational Runbook (doc 15) covers operational procedures.",
            "expected_entities": ["Fraud Detection Engine"],
            "hop_count": 0,
            "category": "cross_document",
            "requires_graph": False,
            "notes": "Tests cross-document awareness for a single entity across 4+ documents"
        },
        {
            "id": "cross_doc_5",
            "question": "How do security requirements trace from regulatory frameworks to technology controls?",
            "expected_answer": "The goal 'Achieve Full Regulatory Compliance' drives GDPR, PCI-DSS, and SOX requirements (doc 16). These map to Data Encryption (doc 06), Role-based Access Control via IAM (doc 06), and audit logging. Technology controls include HSM Appliance for key management and Elasticsearch for log aggregation.",
            "expected_entities": ["Achieve Full Regulatory Compliance", "GDPR Compliance", "PCI-DSS Level 1 Certification", "SOX Audit Trail", "HSM Appliance", "Identity & Access Management"],
            "hop_count": 3,
            "category": "cross_document",
            "requires_graph": True,
            "notes": "Spans docs 06 (security), 12 (roadmap), 16 (compliance)"
        },
        {
            "id": "cross_doc_6",
            "question": "Describe the end-to-end claims processing flow from customer to settlement, including systems and infrastructure.",
            "expected_answer": "Customer submits via Self-Service Portal or Call Center -> CRM System creates Customer Record -> Claims Management Platform creates Claim Record (Claims Registration) -> Claims Assessment via Workflow Engine -> Risk Engine evaluates -> Fraud Detection Engine screens -> Notification Service sends updates -> Billing System processes payment. Infrastructure: all run on Kubernetes/Docker on App Server Cluster, PostgreSQL for persistence.",
            "expected_entities": ["Customer", "Customer Self-Service Portal", "CRM System", "Claims Management Platform", "Workflow Engine", "Risk Engine", "Fraud Detection Engine", "Notification Service", "Billing System", "Kubernetes", "PostgreSQL 15"],
            "hop_count": 4,
            "category": "cross_document",
            "requires_graph": True,
            "notes": "End-to-end flow spanning docs 04, 05, 02, 03, 07"
        },
        # ── Entity Resolution (4) ──
        {
            "id": "entity_resolution_1",
            "question": "Are 'Salesforce CRM', 'Customer Management Platform', and 'CRM System' the same entity?",
            "expected_answer": "Yes, they are all aliases for the CRM System application component. It appears in multiple documents with different names.",
            "expected_entities": ["CRM System"],
            "hop_count": 0,
            "category": "entity_resolution",
            "requires_graph": False,
            "notes": "Tests alias resolution -- CRM System has 3 aliases"
        },
        {
            "id": "entity_resolution_2",
            "question": "What is the relationship between 'PAS', 'Guidewire PolicyCenter', and 'Policy Administration System'?",
            "expected_answer": "They are all names for the same application component: the Policy Administration System. Different documents use different names.",
            "expected_entities": ["Policy Administration System"],
            "hop_count": 0,
            "category": "entity_resolution",
            "requires_graph": False,
            "notes": "Tests alias resolution for PAS"
        },
        {
            "id": "entity_resolution_3",
            "question": "Is 'First Notice of Loss' the same as 'Claims Registration'?",
            "expected_answer": "Yes, FNOL (First Notice of Loss) is an alias for the Claims Registration business process.",
            "expected_entities": ["Claims Registration"],
            "hop_count": 0,
            "category": "entity_resolution",
            "requires_graph": False,
        },
        {
            "id": "entity_resolution_4",
            "question": "When documents mention 'K8s', 'the container orchestration platform', and 'Kubernetes Cluster', are they referring to the same thing?",
            "expected_answer": "Yes, they are all aliases for Kubernetes, the system software used for container orchestration.",
            "expected_entities": ["Kubernetes"],
            "hop_count": 0,
            "category": "entity_resolution",
            "requires_graph": False,
        },
        # ── Completeness (2) ──
        {
            "id": "completeness_1",
            "question": "List all application components in the ArchiSurance architecture.",
            "expected_answer": "CRM System, Policy Administration System, Claims Management Platform, Risk Engine, Customer Self-Service Portal, Document Management System, Notification Service, Fraud Detection Engine, Reporting & Analytics Platform, Enterprise Service Bus, Identity & Access Management, Billing System, Broker Portal, Data Warehouse, Workflow Engine, API Gateway, Content Delivery Network, Email Service, Mobile App Backend, Batch Processing Engine",
            "expected_entities": ENTITIES["ApplicationComponent"],
            "hop_count": 0,
            "category": "completeness",
            "requires_graph": False,
            "notes": "Tests extraction completeness -- should find all 20 ApplicationComponents"
        },
        {
            "id": "completeness_2",
            "question": "List all strategic goals defined in the ArchiSurance architecture.",
            "expected_answer": "Reduce Claims Processing Time by 40%, Achieve 99.9% System Availability, Increase Customer Satisfaction to NPS 60+, Automate 80% of Underwriting Decisions, Zero Data Breaches by 2026, Reduce IT Operational Costs by 25%, Achieve Full Regulatory Compliance, Migrate 100% Workloads to Cloud by 2027",
            "expected_entities": ENTITIES["Goal"],
            "hop_count": 0,
            "category": "completeness",
            "requires_graph": False,
            "notes": "Tests extraction completeness -- should find all 8 Goals"
        },
        # ── Graph advantage (2) ──
        {
            "id": "graph_advantage_1",
            "question": "What is the full dependency chain from the Load Balancer F5 to business goals?",
            "expected_answer": "Load Balancer F5 is assigned to DMZ Network. Firewall Palo Alto also connects DMZ to Corporate LAN. Through the network, traffic reaches the App Server Cluster running Kubernetes, which hosts the Claims Management Platform and Risk Engine. These serve Claims processes linked to the goal 'Reduce Claims Processing Time by 40%' and the system availability goal.",
            "expected_entities": ["Load Balancer F5", "DMZ Network", "App Server Cluster", "Kubernetes", "Claims Management Platform", "Reduce Claims Processing Time by 40%"],
            "hop_count": 5,
            "category": "graph_advantage",
            "requires_graph": True,
            "notes": "Deep traversal that vector search alone cannot answer"
        },
        {
            "id": "graph_advantage_2",
            "question": "If the HSM Appliance fails, what is the blast radius across all architecture layers?",
            "expected_answer": "HSM Appliance realizes Secrets Management Service and Certificate Management Service. Without secrets, all TLS certificates expire affecting all network communication. All applications relying on encrypted connections (CRM, PAS, Claims Platform, etc.) would be impacted. PCI-DSS compliance for the Billing System would be violated. The goal 'Zero Data Breaches by 2026' would be at risk.",
            "expected_entities": ["HSM Appliance", "Secrets Management Service", "Certificate Management Service", "Zero Data Breaches by 2026", "Data Encryption at Rest and in Transit"],
            "hop_count": 4,
            "category": "graph_advantage",
            "requires_graph": True,
            "notes": "Tests deep impact analysis across all layers"
        },
    ]


# ===========================================================================
# Main entry point
# ===========================================================================

DOC_GENERATORS = [
    ("doc_01_enterprise_overview.pdf", gen_doc_01),
    ("doc_02_application_portfolio.pdf", gen_doc_02),
    ("doc_03_infrastructure_design.pdf", gen_doc_03),
    ("doc_04_crm_business_process.pdf", gen_doc_04),
    ("doc_05_claims_processing.pdf", gen_doc_05),
    ("doc_06_security_architecture.pdf", gen_doc_06),
    ("doc_07_integration_architecture.pdf", gen_doc_07),
    ("doc_08_data_architecture.pdf", gen_doc_08),
    ("doc_09_cloud_migration.pdf", gen_doc_09),
    ("doc_10_disaster_recovery.pdf", gen_doc_10),
    ("doc_11_network_architecture.pdf", gen_doc_11),
    ("doc_12_strategic_roadmap.pdf", gen_doc_12),
    ("doc_13_service_catalog.pdf", gen_doc_13),
    ("doc_14_vendor_assessment.pdf", gen_doc_14),
    ("doc_15_operational_runbook.pdf", gen_doc_15),
    ("doc_16_compliance_regulatory.pdf", gen_doc_16),
    ("doc_17_erp_migration.pdf", gen_doc_17),
]


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gt_dir = os.path.join(base_dir, "..", "ground_truth")
    os.makedirs(gt_dir, exist_ok=True)

    # Remove old PDFs
    for f in os.listdir(base_dir):
        if f.endswith(".pdf"):
            os.remove(os.path.join(base_dir, f))

    # Generate all documents
    print(f"Generating {len(DOC_GENERATORS)} PDF documents...\n")
    total_pages = 0
    for filename, gen_func in DOC_GENERATORS:
        pdf, doc_id = gen_func()
        path = os.path.join(base_dir, filename)
        pdf.output(path)
        pages = pdf.page
        total_pages += pages
        size_kb = os.path.getsize(path) / 1024
        entities_in_doc = len(_doc_entities.get(doc_id, set()))
        print(f"  {filename:45s}  {pages:3d} pages  {size_kb:6.0f} KB  {entities_in_doc:3d} entities")

    print(f"\nTotal: {len(DOC_GENERATORS)} documents, {total_pages} pages")

    # Ground truth
    gt = _build_ground_truth()
    gt_path = os.path.join(gt_dir, "archisurance_ground_truth.json")
    with open(gt_path, "w") as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)
    print(f"\nGround truth: {gt_path}")
    print(f"  {gt['total_entities']} entities, {gt['relationship_count']} relationships")
    print(f"  {len(gt['document_entity_presence'])} documents with entity presence data")

    # Entity aliases
    aliases = _build_entity_aliases()
    alias_path = os.path.join(gt_dir, "entity_aliases.json")
    with open(alias_path, "w") as f:
        json.dump(aliases, f, indent=2, ensure_ascii=False)
    print(f"\nEntity aliases: {alias_path}")
    print(f"  {len(aliases)} entities with aliases, {sum(len(v) for v in aliases.values())} total aliases")

    # Eval questions
    questions = _build_eval_questions()
    eq_path = os.path.join(gt_dir, "eval_questions.json")
    with open(eq_path, "w") as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)
    print(f"\nEval questions: {eq_path}")
    categories = {}
    for q in questions:
        categories[q["category"]] = categories.get(q["category"], 0) + 1
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
