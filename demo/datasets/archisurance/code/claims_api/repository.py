"""Database access functions for ClaimsDB and PolicyDB.

These functions wrap a SQLAlchemy session. For demo simplicity the
session lifecycle is omitted; in production each call would obtain a
session from a connection-pooled engine bound to CloudSQL Postgres.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from .models import Claim, Customer, DamageReport, FraudScore, Policy, Settlement


_HANDLER_POOL = [101, 102, 103, 104]
_handler_cursor = 0


def get_customer(customer_id: int) -> Optional[Customer]:
    raise NotImplementedError


def get_policy(policy_id: int) -> Optional[Policy]:
    raise NotImplementedError


def get_claim(claim_id: int) -> Optional[Claim]:
    raise NotImplementedError


def latest_damage_report(claim_id: int) -> Optional[DamageReport]:
    raise NotImplementedError


def create_claim(policy_id: int, amount_requested: Decimal) -> Claim:
    raise NotImplementedError


def update_claim_handler(claim_id: int, handler_id: int) -> None:
    raise NotImplementedError


def create_settlement(claim_id: int, amount_paid: Decimal) -> Settlement:
    raise NotImplementedError


def persist_fraud_score(claim_id: int, score: float, model_version: str) -> FraudScore:
    raise NotImplementedError


def next_available_handler() -> int:
    global _handler_cursor
    handler = _HANDLER_POOL[_handler_cursor % len(_HANDLER_POOL)]
    _handler_cursor += 1
    return handler


def invoke_fraud_scorer(claim_id: int) -> float:
    """Call FraudScorer gRPC service."""
    from fraud_scorer.main import score_claim_remote
    return score_claim_remote(claim_id)
