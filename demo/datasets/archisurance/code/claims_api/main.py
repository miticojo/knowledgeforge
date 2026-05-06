"""ClaimsAPI FastAPI application.

Realises the Claim Intake Service and Payout Service business services
described in ``architecture/01-business-architecture.md``.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import services, repository, events

app = FastAPI(title="ClaimsAPI", version="0.1.0")


class ClaimIn(BaseModel):
    policy_id: int
    amount_requested: float
    incident_summary: str


class ClaimOut(BaseModel):
    id: int
    status: str
    amount_requested: float


@app.post("/v1/claims", response_model=ClaimOut)
def file_claim(payload: ClaimIn) -> ClaimOut:
    """Submit a new claim. Implements the submitClaim application service."""
    claim = services.submit_claim(
        policy_id=payload.policy_id,
        amount_requested=payload.amount_requested,
        incident_summary=payload.incident_summary,
    )
    events.publish_claim_filed(claim_id=claim.id)
    return ClaimOut(id=claim.id, status=claim.status, amount_requested=claim.amount_requested)


@app.get("/v1/claims/{claim_id}", response_model=ClaimOut)
def get_claim(claim_id: int) -> ClaimOut:
    claim = repository.get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return ClaimOut(id=claim.id, status=claim.status, amount_requested=claim.amount_requested)


@app.get("/v1/policies/{policy_id}")
def get_policy(policy_id: int) -> dict:
    policy = repository.get_policy(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="policy not found")
    return {"id": policy.id, "plan": policy.plan, "premium": float(policy.premium)}


@app.post("/v1/claims/{claim_id}/settle")
def settle(claim_id: int) -> dict:
    """Compute and persist a settlement. Realises the Payout Service."""
    settlement = services.compute_settlement(claim_id)
    events.publish_claim_settled(claim_id=claim_id, amount=settlement.amount_paid)
    return {"claim_id": claim_id, "amount_paid": float(settlement.amount_paid)}
