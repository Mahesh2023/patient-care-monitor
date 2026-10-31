"""Pydantic request / response models (strict input validation)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional  # noqa: UP035

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


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
    totp_enabled: bool = False
    created_at: datetime


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class MfaChallengeOut(BaseModel):
    mfa_required: bool = True
    mfa_token: str


class MfaVerifyIn(BaseModel):
    mfa_token: str = Field(max_length=2048)
    code: str = Field(min_length=6, max_length=32, description="6-digit TOTP or a recovery code")


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class TotpCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class TotpDisableIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=32)


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class AuditOut(_ORM):
    id: int
    ts: datetime
    user_id: Optional[uuid.UUID]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    patient_id: Optional[uuid.UUID]
    success: bool
    detail: Optional[dict[str, Any]]


# ---- patients -------------------------------------------------------
class PatientIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=500)


class PatientOut(_ORM):
    id: uuid.UUID
    display_name: str
    notes: Optional[str]
    created_at: datetime
    role: str = "owner"
    baseline_updated_at: Optional[datetime] = None


class AlertSettingsIn(BaseModel):
    """Per-patient alarm configuration (AACN: individualise alarm parameters)."""
    pspi_moderate: float = Field(default=4.0, ge=1.0, le=15.0)
    pspi_severe: float = Field(default=8.0, ge=2.0, le=16.0)
    hr_high: float = Field(default=100.0, ge=70.0, le=180.0)
    hr_low: float = Field(default=60.0, ge=30.0, le=90.0)
    rr_high: float = Field(default=24.0, ge=14.0, le=40.0)
    rr_low: float = Field(default=10.0, ge=4.0, le=14.0)
    cooldown_s: float = Field(default=30.0, ge=0.0, le=3600.0)
    consecutive: int = Field(default=5, ge=1, le=100)
    muted: list[Literal["severe_pain", "moderate_pain", "tachycardia", "bradycardia", "tachypnea",
                        "bradypnea", "vocal_distress", "low_comfort"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ordered(self):
        if self.pspi_severe <= self.pspi_moderate:
            raise ValueError("pspi_severe must be greater than pspi_moderate")
        if self.hr_low >= self.hr_high or self.rr_low >= self.rr_high:
            raise ValueError("low limits must be below high limits")
        return self


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["viewer", "editor"] = "viewer"


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    created_at: Optional[datetime] = None


CARE_EVENT_KINDS = ("medication", "repositioning", "comfort_measure", "meal", "toileting",
                    "visit", "sleep", "other")


class CareEventIn(BaseModel):
    kind: Literal["medication", "repositioning", "comfort_measure", "meal", "toileting", "visit", "sleep", "other"]
    note: Optional[str] = Field(default=None, max_length=300)
    occurred_at: Optional[datetime] = None


class CareEventOut(_ORM):
    id: uuid.UUID
    patient_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    kind: str
    note: Optional[str]
    occurred_at: datetime


class WindowStats(BaseModel):
    minutes: int
    face_samples: int
    avg_pspi: Optional[float]
    max_pspi: Optional[float]
    avg_comfort: Optional[float]
    avg_hr: Optional[float]
    avg_rr: Optional[float]
    alerts: int


class ImpactOut(BaseModel):
    event: CareEventOut
    before: WindowStats
    after: WindowStats
    delta_avg_pspi: Optional[float]
    delta_avg_comfort: Optional[float]
    note: str = "Observational comparison only; not evidence of treatment effect."


class PainadIn(BaseModel):
    breathing: int = Field(ge=0, le=2)
    negative_vocalization: int = Field(ge=0, le=2)
    facial_expression: int = Field(ge=0, le=2)
    body_language: int = Field(ge=0, le=2)
    consolability: int = Field(ge=0, le=2)
    session_id: Optional[uuid.UUID] = None
    auto_items: Optional[dict[str, Optional[int]]] = None
    note: Optional[str] = Field(default=None, max_length=300)


class PainadOut(_ORM):
    id: uuid.UUID
    patient_id: uuid.UUID
    session_id: Optional[uuid.UUID]
    user_id: Optional[uuid.UUID]
    breathing: int
    negative_vocalization: int
    facial_expression: int
    body_language: int
    consolability: int
    total: int
    interpretation: str = ""
    auto_items: Optional[dict[str, Any]]
    note: Optional[str]
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
    escalated_at: Optional[datetime] = None


class MetricOut(_ORM):
    bucket_start: datetime
    samples: int
    face_samples: int
    avg_pspi: float
    max_pspi: float
    avg_comfort: Optional[float]
    avg_arousal: Optional[float]
    avg_hr: Optional[float]
    avg_rr: Optional[float] = None
    alerts: int


class PatientExport(BaseModel):
    patient: PatientOut
    sessions: list[SessionOut]
    alerts: list[AlertOut]
    metrics: list[MetricOut]
    policy: str
