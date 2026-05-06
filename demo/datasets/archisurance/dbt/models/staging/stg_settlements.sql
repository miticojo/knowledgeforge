select
    id          as settlement_id,
    claim_id,
    amount_paid,
    paid_at
from {{ source('claims_raw', 'settlements') }}
