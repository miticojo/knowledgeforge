-- Fact table: one row per claim with policy + settlement attributes.
select
    c.claim_id,
    c.policy_id,
    p.customer_id,
    p.plan,
    c.status,
    c.filed_at,
    c.amount_requested,
    s.amount_paid,
    s.paid_at,
    case when s.paid_at is not null
         then date_diff('hour', c.filed_at, s.paid_at)
    end as cycle_hours
from {{ ref('stg_claims') }} c
left join {{ ref('stg_policies') }} p on p.policy_id = c.policy_id
left join {{ ref('stg_settlements') }} s on s.claim_id = c.claim_id
