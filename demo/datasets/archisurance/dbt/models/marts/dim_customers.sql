-- Customer dimension joined with policy counts.
with customers as (
    select * from {{ source('claims_raw', 'customers') }}
),
policy_counts as (
    select customer_id, count(*) as policy_count
    from {{ ref('stg_policies') }}
    group by customer_id
)
select
    c.id        as customer_id,
    c.name,
    c.email,
    c.created_at,
    coalesce(p.policy_count, 0) as policy_count
from customers c
left join policy_counts p on p.customer_id = c.id
