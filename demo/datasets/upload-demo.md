# ArchiSurance Claim Intake Process

## Business Context
The Customer files a claim through the ClaimHandler.
The ClaimHandler triggers the ClaimsAPI which realizes
the ClaimIntakeService and the PayoutService.

## Application Layer
The FraudScorer (ApplicationComponent) accesses the
ClaimsTable (DataObject) to compute risk scores.

Settlements are persisted to PostgresDB (SystemSoftware).

## Goals
- Reduce ClaimCycleTime
- Detect fraud early
