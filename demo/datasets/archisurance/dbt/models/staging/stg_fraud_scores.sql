select
    id          as fraud_score_id,
    claim_id,
    score,
    model_version,
    scored_at
from {{ source('claims_raw', 'fraud_scores') }}
