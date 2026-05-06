-- ArchiSurance Claims Processing — DDL for ClaimsDB and PolicyDB.
-- Mirrors the data objects described in architecture/04-data-model.md.

CREATE TYPE claim_status AS ENUM ('filed','validated','assessed','approved','paid','rejected');
CREATE TYPE severity AS ENUM ('low','medium','high','total_loss');
CREATE TYPE claim_event_type AS ENUM ('filed','validated','assessed','approved','paid','rejected','scored');

CREATE TABLE customers (
  id          BIGSERIAL PRIMARY KEY,
  name        VARCHAR(200) NOT NULL,
  email       VARCHAR(320) NOT NULL UNIQUE,
  created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE policies (
  id              BIGSERIAL PRIMARY KEY,
  customer_id     BIGINT NOT NULL REFERENCES customers(id),
  plan            VARCHAR(50) NOT NULL,
  premium         NUMERIC(10,2) NOT NULL,
  effective_from  TIMESTAMP NOT NULL,
  expires_on      TIMESTAMP NOT NULL
);

CREATE TABLE claims (
  id                BIGSERIAL PRIMARY KEY,
  policy_id         BIGINT NOT NULL REFERENCES policies(id),
  status            claim_status NOT NULL DEFAULT 'filed',
  filed_at          TIMESTAMP NOT NULL DEFAULT NOW(),
  amount_requested  NUMERIC(12,2) NOT NULL,
  handler_id        BIGINT
);

CREATE TABLE damage_reports (
  id              BIGSERIAL PRIMARY KEY,
  claim_id        BIGINT NOT NULL REFERENCES claims(id),
  photos_uri      VARCHAR(500),
  severity        severity NOT NULL,
  repair_estimate NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE settlements (
  id           BIGSERIAL PRIMARY KEY,
  claim_id     BIGINT NOT NULL UNIQUE REFERENCES claims(id),
  amount_paid  NUMERIC(12,2) NOT NULL,
  paid_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE fraud_scores (
  id            BIGSERIAL PRIMARY KEY,
  claim_id      BIGINT NOT NULL REFERENCES claims(id),
  score         NUMERIC(4,3) NOT NULL,
  model_version VARCHAR(50) NOT NULL,
  scored_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE claim_events (
  id          BIGSERIAL PRIMARY KEY,
  claim_id    BIGINT NOT NULL REFERENCES claims(id),
  event_type  claim_event_type NOT NULL,
  payload     JSONB,
  occurred_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_claims_policy_id ON claims(policy_id);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claim_events_claim_id ON claim_events(claim_id);
CREATE INDEX idx_fraud_scores_claim_id ON fraud_scores(claim_id);
