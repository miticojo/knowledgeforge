# ArchiSurance Claims Processing — Business Architecture

This document describes the business layer of the ArchiSurance Claims
subsystem. It is themed after The Open Group ArchiSurance reference
architecture; all entity names, processes, and narratives below are
synthetic and original to the KnowledgeForge demo dataset.

## Business Actors

- **Customer** — policyholder who initiates a claim after an incident.
- **Claim Handler** — internal employee who triages and progresses claims.
- **Underwriter** — validates that the policy covers the reported event.
- **Fraud Investigator** — reviews claims flagged by the FraudScorer.
- **External Garage** — third-party body shop that submits repair estimates.

## Business Processes

1. **File Claim** — Customer submits a new claim through the customer portal
   or call centre. Captures incident metadata and references the policy.
2. **Validate Claim** — Underwriter confirms policy coverage and checks for
   exclusions. Realised by the `submitClaim` application service.
3. **Assess Damage** — Claim Handler coordinates with External Garage to
   produce a Damage Report and a repair estimate.
4. **Approve Settlement** — Underwriter and Claim Handler agree on a
   settlement amount, optionally informed by the Fraud Score.
5. **Pay Settlement** — Finance triggers payment to the Customer or directly
   to the External Garage.

## Business Services

- **Claim Intake Service** — public-facing service exposing claim filing.
  Realised by the `ClaimsAPI` application component.
- **Damage Assessment Service** — internal service orchestrating damage
  reports and fraud scoring. Realised by `ClaimsWorker` and `FraudScorer`.
- **Payout Service** — settles approved claims. Realised by `ClaimsAPI`
  and the downstream payment integration.

## Business Objects

- **Claim** — the central case record. Lifecycle: filed → validated →
  assessed → approved → paid (or rejected at any step).
- **Policy** — contractual coverage. Owned by the Customer.
- **Customer** — the natural person or legal entity holding the policy.
- **Damage Report** — captures severity, photos, and repair estimate.
- **Settlement** — the financial conclusion of a claim.

## Goals

- **Reduce claim cycle time** from days to hours for low-severity cases.
- **Detect fraud early** so investigators are engaged before payout.
- **Improve customer satisfaction** through transparent status updates.

## Realisation Map

| Business Service          | Realised By                        |
|---------------------------|------------------------------------|
| Claim Intake Service      | ClaimsAPI                          |
| Damage Assessment Service | ClaimsWorker, FraudScorer          |
| Payout Service            | ClaimsAPI, NotificationService     |

The Damage Assessment Service depends on the Claim Intake Service, and
the Payout Service depends on the Damage Assessment Service. Together
they form the end-to-end claims value stream owned by the Claims
business capability.
