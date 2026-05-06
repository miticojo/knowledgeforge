"""Data models for the Risk Engine.

Maps to ArchiMate DataObjects: Risk Score, Premium Calculation Data, Fraud Score Dataset.
"""
from pydantic import BaseModel
from typing import Optional


class RiskScoreRequest(BaseModel):
    """Input for risk evaluation -- maps to Claim Record DataObject."""
    claim_id: str
    customer_id: str
    policy_id: str
    claim_type: str  # AUTO, HEALTH, PROPERTY, LIABILITY
    claim_amount: float
    days_since_policy_start: int
    previous_claims_count: int = 0


class FraudIndicator(BaseModel):
    """Fraud signal -- part of Fraud Score Dataset DataObject."""
    name: str
    weight: float
    description: str = ""


class RiskScoreResponse(BaseModel):
    """Output of risk evaluation -- Risk Score DataObject."""
    claim_id: str
    risk_score: float  # 0.0 to 1.0
    risk_level: str  # LOW, MEDIUM, HIGH
    fraud_indicators: list[FraudIndicator] = []


class PremiumRequest(BaseModel):
    """Input for premium calculation -- Policy Record DataObject."""
    policy_id: str
    customer_id: str
    coverage_amount: float
    risk_score: float


class PremiumResponse(BaseModel):
    """Output of premium calculation -- Premium Calculation Data DataObject."""
    policy_id: str
    annual_premium: float
    risk_multiplier: float
