-- Fact: claims joined with their latest fraud score; flag high risk.
with latest_scores as (
    select claim_id, max(scored_at) as scored_at
    from {{ ref('stg_fraud_scores') }}
    group by claim_id
),
scores as (
    select s.claim_id, s.score, s.model_version, s.scored_at
    from {{ ref('stg_fraud_scores') }} s
    inner join latest_scores l
        on l.claim_id = s.claim_id and l.scored_at = s.scored_at
)
select
    c.claim_id,
    c.policy_id,
    c.status,
    c.amount_requested,
    s.score          as fraud_score,
    s.model_version,
    case when s.score >= 0.8 then true else false end as is_high_risk
from {{ ref('stg_claims') }} c
left join scores s on s.claim_id = c.claim_id
