-- Staging model for claims data
-- Source: Claims Management Platform → PostgreSQL 15 → raw_claims.claims
-- DataObject: Claim Record (staged)
--
-- INTENTIONAL VIOLATION (DBT-003): Should use source(), not direct table reference
-- Correct: {{ source('raw_claims', 'claims') }}

SELECT
    claim_id,
    customer_id,
    policy_id,
    claim_type,
    CAST(amount AS NUMERIC) AS claim_amount,
    status AS claim_status,
    TIMESTAMP(created_at) AS registered_at,
    CURRENT_TIMESTAMP() AS _loaded_at
FROM
    `archisurance_raw.claims.claims`  -- VIOLATION: Direct table reference instead of source()
WHERE
    claim_id IS NOT NULL
