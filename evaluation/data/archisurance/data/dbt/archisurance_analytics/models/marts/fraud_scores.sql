-- Fraud scoring mart — DataObject: Fraud Score Dataset
-- Consumed by: Fraud Detection Engine (ApplicationComponent)
-- Sources: stg_claims + raw_fraud_external
--
-- INTENTIONAL VIOLATION (DBT-004): No materialization specified
-- Should have: {{ config(materialized='table') }}

WITH claims AS (
    SELECT * FROM {{ ref('stg_claims') }}
),

fraud_signals AS (
    -- INTENTIONAL VIOLATION: Accessing raw table directly instead of staged
    SELECT * FROM `archisurance_external.fraud.fraud_signals`
),

scored AS (
    SELECT
        c.claim_id,
        c.customer_id,
        c.claim_amount,
        c.claim_status,
        COALESCE(f.risk_score, 0.0) AS external_fraud_score,
        CASE
            WHEN c.claim_amount > 50000 THEN 0.3
            WHEN c.claim_amount > 10000 THEN 0.1
            ELSE 0.0
        END AS amount_risk_factor,
        COALESCE(f.risk_score, 0.0) +
        CASE WHEN c.claim_amount > 50000 THEN 0.3 ELSE 0.0 END AS combined_fraud_score
    FROM claims c
    LEFT JOIN fraud_signals f ON c.claim_id = f.claim_id
)

SELECT * FROM scored
