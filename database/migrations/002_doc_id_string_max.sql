-- Migration 002: Widen doc_id columns from STRING(36) to STRING(MAX).
--
-- Motivation
-- ----------
-- The git ingester synthesises doc_ids of the form
--     git:<repo_url>@<commit_sha>:<file_path>
-- which routinely exceed 36 characters (often >100). Writes failed with:
--     New value exceeds the maximum size limit for this column:
--         Documents.doc_id, size: 111, limit: 36
--
-- Cloud Spanner allows widening a STRING column without a table rewrite, so
-- this migration is safe to apply in-place against production data.
--
-- Idempotency
-- -----------
-- Spanner ALTER COLUMN is itself idempotent: re-running an ALTER that sets the
-- column to its current declared type is a no-op (it returns success without
-- touching data). The init_emulator runner additionally treats
-- "already exists" / duplicate errors as skip-and-continue, so this migration
-- can be re-applied any number of times without manual intervention.
--
-- Run with:
--   gcloud spanner databases ddl update "$SPANNER_DATABASE" \
--     --instance="$SPANNER_INSTANCE" --ddl-file=migrations/002_doc_id_string_max.sql

ALTER TABLE Documents        ALTER COLUMN doc_id STRING(MAX) NOT NULL;
ALTER TABLE DocumentChunks   ALTER COLUMN doc_id STRING(MAX) NOT NULL;
ALTER TABLE DocumentMentions ALTER COLUMN doc_id STRING(MAX) NOT NULL;
ALTER TABLE ChunkMentions    ALTER COLUMN doc_id STRING(MAX) NOT NULL;
