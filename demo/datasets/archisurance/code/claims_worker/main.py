"""ClaimsWorker entrypoint.

Subscribes to the ``claims.events`` Pub/Sub topic and orchestrates
fraud scoring + notification fan-out.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from claims_api import services as claims_services
from claims_api import events as claims_events

log = logging.getLogger("claims_worker")


def handle_event(message_data: bytes) -> None:
    event = json.loads(message_data.decode("utf-8"))
    event_type = event.get("event_type")
    payload: dict[str, Any] = event.get("payload", {})
    claim_id = payload.get("claim_id")
    if claim_id is None:
        return

    if event_type == "filed":
        score = claims_services.score_fraud(claim_id)
        claims_events.publish_claim_scored(claim_id, score)
    elif event_type == "scored":
        # high-risk routing handled here in production
        log.info("claim %s scored=%s", claim_id, payload.get("score"))
    elif event_type == "paid":
        claims_events.send_notification(claim_id, "Your claim has been paid.")


def run_forever() -> None:
    """Production entrypoint: polls the subscription and dispatches."""
    raise NotImplementedError("wire up google.cloud.pubsub_v1.SubscriberClient")


if __name__ == "__main__":
    run_forever()
