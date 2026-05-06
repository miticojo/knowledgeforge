-- Multi-tenancy: Add tenant_id to all tables
-- Existing rows get DEFAULT '__shared__' (benchmark data)
-- Run with:
--   gcloud spanner databases ddl update "$SPANNER_DATABASE" \
--     --instance="$SPANNER_INSTANCE" --ddl-file=add_tenant_id.ddl

ALTER TABLE Documents ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE BusinessActors ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE BusinessRoles ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE BusinessProcesses ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE BusinessFunctions ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE BusinessServices ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE BusinessObjects ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Contracts ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE ApplicationComponents ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE ApplicationServices ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE ApplicationInterfaces ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE DataObjects ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Nodes ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE SystemSoftwares ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE TechnologyServices ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Artifacts ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Devices ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE CommunicationNetworks ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Requirements ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Goals ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Constraints ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Stakeholders ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Capabilities ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE DocumentMentions ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE DocumentChunks ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE ChunkMentions ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Composition ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Aggregation ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Assignment ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Realization ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Serving ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Access ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Triggering ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Flow ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Influence ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Association ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');
ALTER TABLE Specialization ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');

CREATE INDEX Idx_Documents_TenantId ON Documents(tenant_id);
CREATE INDEX Idx_DocumentChunks_TenantId ON DocumentChunks(tenant_id);
