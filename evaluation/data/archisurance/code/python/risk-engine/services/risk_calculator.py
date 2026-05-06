"""Risk Engine -- core ApplicationComponent for risk assessment.

Implements the Risk Assessment Intelligence capability.
Serves Risk Evaluation and Premium Calculation business processes.
Accesses Risk Score and Premium Calculation Data data objects.
"""
import logging
from ..models.risk_models import (
    RiskScoreRequest, RiskScoreResponse,
    PremiumRequest, PremiumResponse,
    FraudIndicator,
)
from ..adapters.kafka_producer import KafkaEventProducer

logger = logging.getLogger(__name__)


class RiskCalculator:
    """Core risk calculation engine (ApplicationComponent: Risk Engine).

    Connected to:
    - Fraud Detection Engine via Kafka events (Flow relationship)
    - Claims Management Platform via REST API (Serving relationship)
    - Data Warehouse for analytics (Access relationship)
    """

    def __init__(self, kafka: KafkaEventProducer = None):
        self.kafka = kafka or KafkaEventProducer()
        self.model_version = "fraud-scoring-model.onnx"  # Artifact reference

    async def evaluate(self, request: RiskScoreRequest) -> RiskScoreResponse:
        """Evaluate risk for a claim. Accesses Risk Score DataObject."""
        base_score = self._calculate_base_risk(request)
        fraud_indicators = self._check_fraud_indicators(request)

        final_score = base_score * (1 + sum(f.weight for f in fraud_indicators))

        # Publish risk event to Apache Kafka for downstream consumers
        await self.kafka.publish("risk.scores", {
            "claim_id": request.claim_id,
            "score": final_score,
            "model_version": self.model_version,
        })

        return RiskScoreResponse(
            claim_id=request.claim_id,
            risk_score=min(final_score, 1.0),
            risk_level="HIGH" if final_score > 0.7 else "MEDIUM" if final_score > 0.3 else "LOW",
            fraud_indicators=fraud_indicators,
        )

    async def calculate_premium(self, request: PremiumRequest) -> PremiumResponse:
        """Calculate premium. Accesses Premium Calculation Data DataObject."""
        base_premium = request.coverage_amount * 0.02  # 2% base rate
        risk_multiplier = 1 + (request.risk_score * 0.5)

        return PremiumResponse(
            policy_id=request.policy_id,
            annual_premium=round(base_premium * risk_multiplier, 2),
            risk_multiplier=round(risk_multiplier, 3),
        )

    def _calculate_base_risk(self, request: RiskScoreRequest) -> float:
        return 0.15 + (request.claim_amount / 100000) * 0.3

    def _check_fraud_indicators(self, request: RiskScoreRequest) -> list[FraudIndicator]:
        indicators = []
        if request.claim_amount > 50000:
            indicators.append(FraudIndicator(name="high_amount", weight=0.2))
        if request.days_since_policy_start < 30:
            indicators.append(FraudIndicator(name="new_policy", weight=0.3))
        return indicators
