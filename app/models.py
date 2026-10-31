"""Relational schema (portable: Postgres in prod, SQLite in tests).

Data-minimisation by design: patients are pseudonymous (display name only),
no raw media is ever stored, IPs are HMAC digests, and high-volume telemetry
is stored only as per-minute aggregates (`session_metrics`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Any, Optional

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Uuid, false,
)
from sqlalchemy.orm import Mapped, mapped_column

from .core.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


TZDateTime = DateTime(timezone=True)
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default="caregiver")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    # TOTP 2FA (RFC 6238). Secret is AES-GCM encrypted at rest; recovery codes are SHA-256 digests.
    totp_secret_enc: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    totp_last_step: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    recovery_codes: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)  # = JWT jti
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    # Neutral-face AU offsets (per-patient calibration) and per-patient alarm config.
    au_baseline: Mapped[Optional[dict[str, float]]] = mapped_column(JSON, nullable=True)
    baseline_updated_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    alert_settings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class PatientMember(Base):
    """Care-team sharing. The patient owner is implicit (patients.owner_id)."""
    __tablename__ = "patient_members"
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16))  # viewer | editor
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class CareEvent(Base):
    """Caregiver-logged interventions, used to compare signals before/after."""
    __tablename__ = "care_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    __table_args__ = (Index("ix_care_events_patient_time", "patient_id", "occurred_at"),)


class PainadAssessment(Base):
    """Caregiver-completed PAINAD (Warden et al. 2003); auto items are suggestions only."""
    __tablename__ = "painad_assessments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("monitoring_sessions.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    breathing: Mapped[int] = mapped_column(Integer)
    negative_vocalization: Mapped[int] = mapped_column(Integer)
    facial_expression: Mapped[int] = mapped_column(Integer)
    body_language: Mapped[int] = mapped_column(Integer)
    consolability: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    auto_items: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    __table_args__ = (Index("ix_painad_patient_created", "patient_id", "created_at"),)


class AuditEvent(Base):
    """Append-only audit trail (HIPAA §164.312(b) audit controls).

    No foreign keys on purpose: the trail must survive erasure of the
    referenced user/patient (ids are pseudonymous; no PII is stored here).
    """
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(48))
    resource_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_hash: Mapped[str] = mapped_column(String(32), default="")
    request_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_audit_user_ts", "user_id", "ts"),
        Index("ix_audit_patient_ts", "patient_id", "ts"),
        Index("ix_audit_ts", "ts"),
    )


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|ended|revoked
    consent_purpose: Mapped[str] = mapped_column(String(64), default="clinical_monitoring")
    consent_granted_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    consent_expires_at: Mapped[datetime] = mapped_column(TZDateTime)
    consent_revoked_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    ip_hash: Mapped[str] = mapped_column(String(32), default="")
    sample_count: Mapped[int] = mapped_column(BigInteger, default=0)
    started_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)

    def consent_valid(self, now: Optional[datetime] = None) -> bool:
        now = now or utcnow()
        exp = self.consent_expires_at
        if exp.tzinfo is None:  # SQLite drops tzinfo
            exp = exp.replace(tzinfo=UTC)
        return self.status == "active" and self.consent_revoked_at is None and now < exp


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitoring_sessions.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(300))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, nullable=True)

    __table_args__ = (
        Index("ix_alerts_patient_created", "patient_id", "created_at"),
        Index("ix_alerts_created", "created_at"),
    )


class SessionMetric(Base):
    __tablename__ = "session_metrics"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitoring_sessions.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    bucket_start: Mapped[datetime] = mapped_column(TZDateTime)
    samples: Mapped[int] = mapped_column(Integer, default=0)
    face_samples: Mapped[int] = mapped_column(Integer, default=0)
    avg_pspi: Mapped[float] = mapped_column(Float, default=0.0)
    max_pspi: Mapped[float] = mapped_column(Float, default=0.0)
    avg_comfort: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_arousal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_rr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alerts: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_metrics_patient_bucket", "patient_id", "bucket_start"),
        Index("ix_metrics_bucket", "bucket_start"),
    )
