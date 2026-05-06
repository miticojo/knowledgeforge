# ArchiSurance Claims Processing — Application Architecture

This document describes the application layer of the ArchiSurance Claims
subsystem. The components below correspond one-to-one to Python modules
under `demo/datasets/archisurance/code/`.

## Application Components

- **ClaimsAPI** — FastAPI service exposing the public REST surface for
  filing and querying claims. Implemented in `claims_api/main.py`.
- **ClaimsWorker** — background processor that consumes `ClaimEvent`
  messages from Pub/Sub and runs orchestration steps (assignment, fraud
  scoring requests, notification fan-out). Implemented in
  `claims_worker/main.py`.
- **FraudScorer** — gRPC/HTTP service that returns a fraud probability
  score per claim. Implemented in `fraud_scorer/main.py`.
- **NotificationService** — fan-out service that sends customer-facing
  status updates (email, SMS). Realised inline in `claims_api/events.py`.
- **PolicyDB** — relational store of policies. CloudSQL Postgres.
- **ClaimsDB** — relational store of claims, damage reports, settlements.
  CloudSQL Postgres. Defined in `sql/schema.sql`.
- **EventBus** — Cloud Pub/Sub topic `claims.events` carrying
  `ClaimEvent` messages.

## Application Services

- **submitClaim** — accepts a new claim, validates the referenced policy,
  persists the Claim record, publishes `ClaimEvent(type=filed)`.
- **scoreClaim** — invokes FraudScorer and persists a `FraudScore`.
- **assignHandler** — picks a Claim Handler based on workload and
  severity. Updates `claims.handler_id`.
- **computeSettlement** — computes the settlement amount from the damage
  report and policy plan.
- **sendNotification** — delivers a status change to the Customer.

## Application Interfaces

- **REST `/v1/claims`** — POST to file a claim, GET to fetch one.
- **REST `/v1/policies/{id}`** — GET policy by id.
- **gRPC `FraudScorer.Score`** — request/response with `claim_id` and
  returns `score`, `model_version`.
- **Pub/Sub topic `claims.events`** — async event delivery.

## Realisation of Business Services

| Application Service | Realises Business Service       |
|---------------------|---------------------------------|
| submitClaim         | Claim Intake Service            |
| assignHandler       | Damage Assessment Service       |
| scoreClaim          | Damage Assessment Service       |
| computeSettlement   | Payout Service                  |
| sendNotification    | Payout Service                  |

## Component Collaboration

ClaimsAPI writes to ClaimsDB and PolicyDB, then publishes a `ClaimEvent`
to the EventBus. ClaimsWorker subscribes, calls FraudScorer over gRPC,
writes back a `FraudScore` row, and (when ready) calls the
NotificationService to inform the Customer. The end-to-end happy path
involves at most three asynchronous hops between filing and notification.

## Deployment

All components run on the `claims-prod` GKE cluster (see Technology
Architecture document). Each component ships as a Docker image stored
in Artifact Registry under the `claims/` repository.
