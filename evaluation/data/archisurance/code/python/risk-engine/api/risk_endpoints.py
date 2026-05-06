"""Risk Scoring API -- ApplicationInterface for the Risk Engine.

Exposes endpoints consumed by Claims Management Platform and
Underwriting Service (ApplicationComponents) for risk evaluation.
"""
from fastapi import APIRouter, Depends
from ..services.risk_calculator import RiskCalculator
from ..models.risk_models import RiskScoreRequest, RiskScoreResponse, PremiumRequest, PremiumResponse

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.post("/score", response_model=RiskScoreResponse)
async def calculate_risk_score(request: RiskScoreRequest, calc: RiskCalculator = Depends()):
    """Calculate risk score for a claim or policy.

    Serves: Risk Evaluation, Premium Calculation (BusinessProcess)
    Accesses: Risk Score, Premium Calculation Data (DataObject)
    """
    return await calc.evaluate(request)


@router.post("/premium", response_model=PremiumResponse)
async def calculate_premium(request: PremiumRequest, calc: RiskCalculator = Depends()):
    """Calculate insurance premium based on risk assessment.

    Serves: Premium Calculation (BusinessProcess)
    Accesses: Premium Calculation Data (DataObject)
    """
    return await calc.calculate_premium(request)


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "risk-engine", "version": "2.1.0"}
