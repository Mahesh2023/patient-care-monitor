"""Pydantic request / response models (strict input validation)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth -----------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int


class UserOut(_ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    created_at: datetime


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


# ---- patients -------------------------------------------------------
class PatientIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=500)


class PatientOut(_ORM):
    id: uuid.UUID
    display_name: str
    notes: Optional[str]
    created_at: datetime


# ---- sessions -------------------------------------------------------
class SessionStartIn(BaseModel):
    patient_id: uuid.UUID
    consent_confirmed: bool = Field(description="Caller attests informed consent was obtained")
    purpose: str = Field(default="clinical_monitoring", max_length=64, pattern=r"^[a-z0-9_]+$")


class SessionOut(_ORM):
    id: uuid.UUID
    patient_id: uuid.UUID
    status: str
    consent_purpose: str
    consent_granted_at: datetime
    consent_expires_at: datetime
    consent_revoked_at: Optional[datetime]
    sample_count: int
    started_at: datetime
    ended_at: Optional[datetime]


class SessionStartOut(BaseModel):
    session: SessionOut
    ws_ticket: str
    ws_path: str = "/ws/ingest"


class TicketOut(BaseModel):
    ws_ticket: str
    ws_path: str


# ---- alerts / metrics ----------------------------------------------
class AlertOut(_ORM):
    id: uuid.UUID
    session_id: uuid.UUID
    patient_id: uuid.UUID
    key: str
    level: str
    reason: str
    evidence: dict[str, Any]
    created_at: datetime
    acknowledged_at: Optional[datetime]


class MetricOut(_ORM):
    bucket_start: datetime
    samples: int
    face_samples: int
    avg_pspi: float
    max_pspi: float
    avg_comfort: Optional[float]
    avg_arousal: Optional[float]
    avg_hr: Optional[float]
    alerts: int


class PatientExport(BaseModel):
    patient: PatientOut
    sessions: list[SessionOut]
    alerts: list[AlertOut]
    metrics: list[MetricOut]
    policy: str
