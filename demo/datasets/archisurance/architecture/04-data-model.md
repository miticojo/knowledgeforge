# ArchiSurance Claims Processing — Data Model

The data model mirrors the SQL DDL in `sql/schema.sql`.

## Data Objects

- **Customer** — id, name, email, created_at.
- **Policy** — id, customer_id, plan, premium, effective_from, expires_on.
- **Claim** — id, policy_id, status, filed_at, amount_requested, handler_id.
- **DamageReport** — id, claim_id, photos_uri, severity, repair_estimate.
- **Settlement** — id, claim_id, amount_paid, paid_at.
- **FraudScore** — id, claim_id, score, model_version, scored_at.
- **ClaimEvent** — id, claim_id, event_type, payload, occurred_at.

## Access by Application Component

| Component         | Data Objects accessed                          |
|-------------------|------------------------------------------------|
| ClaimsAPI         | Claim, Policy, Customer, DamageReport, Settlement |
| ClaimsWorker      | ClaimEvent, Claim, FraudScore                  |
| FraudScorer       | (reads features from request payload only)     |
| dbt analytics     | BigQuery views over Claim, Policy, Settlement, FraudScore |

## Lifecycle

A Claim transitions through statuses `filed` → `validated` → `assessed`
→ `approved` → `paid`, with terminal state `rejected` reachable from any
non-terminal state. Each transition is recorded as a row in
`claim_events`.

## Analytics Views

The dbt project (`dbt/`) materialises three marts that downstream
dashboards consume:

- `dim_customers` — denormalised customer dimension.
- `fct_claim_lifecycle` — one row per claim with timestamps for each
  status transition and joined policy and settlement attributes.
- `fct_fraud_signals` — joins claims with fraud scores and flags claims
  whose score exceeds the configured threshold.

## Privacy

`customers.email` is classified as PII and is masked in BigQuery via a
column-level policy tag `pii.email`. Photos in `claims-attachments`
inherit the bucket-level CMEK and are subject to a 7-year retention
policy aligned with regulatory requirements.
