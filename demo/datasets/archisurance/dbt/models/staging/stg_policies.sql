select
    id            as policy_id,
    customer_id,
    plan,
    premium,
    effective_from,
    expires_on
from {{ source('claims_raw', 'policies') }}
