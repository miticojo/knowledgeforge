-- Migration 001: Add confidence column to all 11 edge tables
-- Values: EXTRACTED (explicit in text), INFERRED (deduced from context), AMBIGUOUS (uncertain)
-- Existing rows will have NULL, treated as EXTRACTED by application code.

ALTER TABLE Composition ADD COLUMN confidence STRING(16);
ALTER TABLE Aggregation ADD COLUMN confidence STRING(16);
ALTER TABLE Assignment ADD COLUMN confidence STRING(16);
ALTER TABLE Realization ADD COLUMN confidence STRING(16);
ALTER TABLE Serving ADD COLUMN confidence STRING(16);
ALTER TABLE Access ADD COLUMN confidence STRING(16);
ALTER TABLE Influence ADD COLUMN confidence STRING(16);
ALTER TABLE Association ADD COLUMN confidence STRING(16);
ALTER TABLE Triggering ADD COLUMN confidence STRING(16);
ALTER TABLE Flow ADD COLUMN confidence STRING(16);
ALTER TABLE Specialization ADD COLUMN confidence STRING(16);
