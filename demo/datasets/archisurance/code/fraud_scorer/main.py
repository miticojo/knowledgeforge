"""FraudScorer FastAPI service plus a remote-call helper.

In production this is served via gRPC (``FraudScorer.Score``) backed by a
Vertex AI endpoint; for the demo we expose a thin FastAPI surface.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="FraudScorer", version="1.2.0")

MODEL_VERSION = "fs-v1.2.0"


class ScoreRequest(BaseModel):
    claim_id: int


class ScoreResponse(BaseModel):
    claim_id: int
    score: float
    model_version: str


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    s = _predict(req.claim_id)
    return ScoreResponse(claim_id=req.claim_id, score=s, model_version=MODEL_VERSION)


def _predict(claim_id: int) -> float:
    """Stub predictor — deterministic in [0, 1) for demo purposes."""
    return ((claim_id * 2654435761) % 1000) / 1000.0


def score_claim_remote(claim_id: int) -> float:
    """Client-side helper used by claims_api.repository.invoke_fraud_scorer."""
    return _predict(claim_id)
