"""Pub/Sub event publishers for the EventBus topic ``claims.events``."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

TOPIC_NAME = "projects/archisurance/topics/claims.events"


def _publish(event_type: str, payload: dict[str, Any]) -> None:
    message = {
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    # In production this calls google.cloud.pubsub_v1.PublisherClient.publish.
    _emit(json.dumps(message).encode("utf-8"))


def _emit(data: bytes) -> None:
    """Stub for the Pub/Sub publisher client."""
    return None


def publish_claim_filed(claim_id: int) -> None:
    _publish("filed", {"claim_id": claim_id})


def publish_claim_scored(claim_id: int, score: float) -> None:
    _publish("scored", {"claim_id": claim_id, "score": score})


def publish_claim_settled(claim_id: int, amount: float) -> None:
    _publish("paid", {"claim_id": claim_id, "amount": float(amount)})


def send_notification(customer_id: int, message: str) -> None:
    """NotificationService entry point."""
    return None
