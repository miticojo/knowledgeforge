"""Application services realising the business services for ClaimsAPI."""
from __future__ import annotations

from decimal import Decimal

from . import repository
from .models import Claim, Settlement


def submit_claim(policy_id: int, amount_requested: float, incident_summary: str) -> Claim:
    """Realises the Claim Intake business service."""
    policy = repository.get_policy(policy_id)
    if policy is None:
        raise ValueError(f"unknown policy {policy_id}")
    claim = repository.create_claim(
        policy_id=policy_id,
        amount_requested=Decimal(str(amount_requested)),
    )
    assign_handler(claim.id)
    return claim


def assign_handler(claim_id: int) -> int:
    """Pick a Claim Handler based on workload (round-robin stub)."""
    handler_id = repository.next_available_handler()
    repository.update_claim_handler(claim_id, handler_id)
    return handler_id


def score_fraud(claim_id: int) -> float:
    """Invoke the FraudScorer gRPC service and persist the result."""
    score = repository.invoke_fraud_scorer(claim_id)
    repository.persist_fraud_score(claim_id, score, model_version="fs-v1.2.0")
    return score


def compute_settlement(claim_id: int) -> Settlement:
    """Realises the Payout business service."""
    claim = repository.get_claim(claim_id)
    if claim is None:
        raise ValueError(f"unknown claim {claim_id}")
    report = repository.latest_damage_report(claim_id)
    if report is None:
        amount = Decimal(claim.amount_requested)
    else:
        amount = min(Decimal(claim.amount_requested), Decimal(report.repair_estimate))
    return repository.create_settlement(claim_id=claim_id, amount_paid=amount)
