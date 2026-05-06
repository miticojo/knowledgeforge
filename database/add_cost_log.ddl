-- Cost tracking: per-operation cost log
CREATE TABLE CostLog (
    log_id STRING(36) NOT NULL,
    tenant_id STRING(320) NOT NULL,
    operation_type STRING(20) NOT NULL,
    operation_id STRING(36),
    total_cost_usd FLOAT64,
    input_tokens INT64,
    output_tokens INT64,
    embed_tokens INT64,
    spanner_reads INT64,
    spanner_writes INT64,
    breakdown JSON,
    created_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
) PRIMARY KEY (log_id);

CREATE INDEX Idx_CostLog_Tenant ON CostLog(tenant_id, created_at DESC);
