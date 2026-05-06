"""SQLAlchemy ORM models for the ClaimsDB and PolicyDB schemas.

Mirrors the DDL in ``sql/schema.sql``.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric, ForeignKey, Enum, JSON,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    email = Column(String(320), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    policies = relationship("Policy", back_populates="customer")


class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    plan = Column(String(50), nullable=False)
    premium = Column(Numeric(10, 2), nullable=False)
    effective_from = Column(DateTime, nullable=False)
    expires_on = Column(DateTime, nullable=False)
    customer = relationship("Customer", back_populates="policies")
    claims = relationship("Claim", back_populates="policy")


class Claim(Base):
    __tablename__ = "claims"
    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=False)
    status = Column(
        Enum("filed", "validated", "assessed", "approved", "paid", "rejected", name="claim_status"),
        nullable=False,
        default="filed",
    )
    filed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    amount_requested = Column(Numeric(12, 2), nullable=False)
    handler_id = Column(Integer, nullable=True)
    policy = relationship("Policy", back_populates="claims")
    damage_reports = relationship("DamageReport", back_populates="claim")
    settlement = relationship("Settlement", back_populates="claim", uselist=False)


class DamageReport(Base):
    __tablename__ = "damage_reports"
    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    photos_uri = Column(String(500), nullable=True)
    severity = Column(Enum("low", "medium", "high", "total_loss", name="severity"), nullable=False)
    repair_estimate = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    claim = relationship("Claim", back_populates="damage_reports")


class Settlement(Base):
    __tablename__ = "settlements"
    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False, unique=True)
    amount_paid = Column(Numeric(12, 2), nullable=False)
    paid_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    claim = relationship("Claim", back_populates="settlement")


class FraudScore(Base):
    __tablename__ = "fraud_scores"
    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    score = Column(Numeric(4, 3), nullable=False)
    model_version = Column(String(50), nullable=False)
    scored_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ClaimEvent(Base):
    __tablename__ = "claim_events"
    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    event_type = Column(
        Enum("filed", "validated", "assessed", "approved", "paid", "rejected", "scored", name="claim_event_type"),
        nullable=False,
    )
    payload = Column(JSON, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)
