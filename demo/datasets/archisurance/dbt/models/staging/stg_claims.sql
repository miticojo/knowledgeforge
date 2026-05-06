-- Staging view: raw claims rows from the OLTP CloudSQL replica.
select
    id              as claim_id,
    policy_id,
    status,
    filed_at,
    amount_requested,
    handler_id
from {{ source('claims_raw', 'claims') }}
