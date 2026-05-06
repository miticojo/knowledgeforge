-- Premium analytics mart — DataObject: Premium Calculation Data
-- Consumed by: Risk Engine, Reporting & Analytics Platform
-- Serves: Premium Calculation, Regulatory Reporting (BusinessProcess)

{{ config(materialized='table', schema='marts') }}

WITH claims AS (
    SELECT * FROM {{ ref('stg_claims') }}
),

fraud AS (
    SELECT * FROM {{ ref('fraud_scores') }}
)

SELECT
    c.policy_id,
    c.customer_id,
    COUNT(c.claim_id) AS total_claims,
    SUM(c.claim_amount) AS total_claim_amount,
    AVG(c.claim_amount) AS avg_claim_amount,
    MAX(f.combined_fraud_score) AS max_fraud_score,
    CASE
        WHEN MAX(f.combined_fraud_score) > 0.7 THEN 'HIGH_RISK'
        WHEN MAX(f.combined_fraud_score) > 0.3 THEN 'MEDIUM_RISK'
        ELSE 'LOW_RISK'
    END AS risk_category,
    CURRENT_TIMESTAMP() AS calculated_at
FROM claims c
LEFT JOIN fraud f ON c.claim_id = f.claim_id
GROUP BY c.policy_id, c.customer_id
