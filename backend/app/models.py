from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class UserRole(str, Enum):
    employee = "employee"
    admin = "admin"


class SessionMode(str, Enum):
    individual = "individual"
    group = "group"


class SessionStatus(str, Enum):
    active = "active"
    finished = "finished"


class PPEState(str, Enum):
    unknown = "unknown"
    present = "present"
    absent = "absent"


class User(BaseModel):
    id: str = Field(default_factory=lambda: new_id("usr"))
    name: str
    username: str
    password_hash: str
    role: UserRole = UserRole.employee
    job_role_id: str | None = None
    area_id: str | None = None
    preset_id: str | None = None
    active: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class UserPublic(BaseModel):
    id: str
    name: str
    username: str
    role: UserRole
    job_role_id: str | None = None
    area_id: str | None = None
    preset_id: str | None = None
    active: bool
    created_at: datetime


class UserCreate(BaseModel):
    name: str
    username: str
    password: str = Field(min_length=6)
    role: UserRole = UserRole.employee
    job_role_id: str | None = None
    area_id: str | None = None
    preset_id: str | None = None
    active: bool = True


class UserUpdate(BaseModel):
    name: str | None = None
    password: str | None = Field(default=None, min_length=6)
    role: UserRole | None = None
    job_role_id: str | None = None
    area_id: str | None = None
    preset_id: str | None = None
    active: bool | None = None


class PPE(BaseModel):
    code: str
    name: str
    positive_class: str
    negative_class: str


class Preset(BaseModel):
    id: str = Field(default_factory=lambda: new_id("pre"))
    name: str
    ppe_codes: list[str]
    active: bool = True


class JobRole(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job"))
    name: str
    preset_id: str | None = None


class Area(BaseModel):
    id: str = Field(default_factory=lambda: new_id("area"))
    name: str
    preset_id: str | None = None


class SeverityPolicy(BaseModel):
    level_1_seconds: float = 2
    level_2_seconds: float = 5
    level_3_seconds: float = 10
    recovery_seconds: float = 3
    window_seconds: float = 3
    present_ratio: float = 0.6
    absent_ratio: float = 0.4


class LatencyMetric(BaseModel):
    frame_id: str
    captured_at_ms: float
    received_at_ms: float
    inference_ms: float
    processing_ms: float
    server_total_ms: float
    e2e_ms: float | None = None


class PPECompliance(BaseModel):
    ppe_code: str
    state: PPEState = PPEState.unknown
    ratio: float = 0
    severity: int = 0
    absent_since: datetime | None = None
    recovered_since: datetime | None = None


class TrackedPersonSummary(BaseModel):
    track_id: str
    user_id: str | None = None
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    samples: int = 0
    compliant_samples: int = 0
    ppe: dict[str, PPECompliance] = Field(default_factory=dict)


class ComplianceSnapshot(BaseModel):
    timestamp: datetime
    track_id: str
    user_id: str | None = None
    ppe_code: str
    state: PPEState
    severity: int = 0
    ratio: float = 0


class MonitoringSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ses"))
    user_id: str
    mode: SessionMode
    preset_id: str | None = None
    required_ppe: list[str]
    status: SessionStatus = SessionStatus.active
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    machine_locked: bool = False
    tracks: dict[str, TrackedPersonSummary] = Field(default_factory=dict)
    latency_metrics: list[LatencyMetric] = Field(default_factory=list)
    timeline: list[ComplianceSnapshot] = Field(default_factory=list)


class SafetyEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evt"))
    session_id: str
    track_id: str
    user_id: str | None = None
    ppe_code: str
    severity: int
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float = 0


class Infraction(BaseModel):
    id: str = Field(default_factory=lambda: new_id("inf"))
    session_id: str
    safety_event_id: str
    user_id: str | None = None
    track_id: str
    ppe_code: str
    occurred_at: datetime = Field(default_factory=utc_now)
    notes: str | None = None


class MachineCommand(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cmd"))
    session_id: str
    action: str
    reason: str
    result: str
    created_at: datetime = Field(default_factory=utc_now)
    reset_by_user_id: str | None = None


class QualityReport(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rep"))
    session_id: str
    generated_at: datetime = Field(default_factory=utc_now)
    duration_seconds: float
    required_ppe: list[str]
    compliance_percent: float
    events_by_severity: dict[str, int]
    infractions: int
    machine_cuts: int
    latency: dict[str, float]
    track_summaries: list[TrackedPersonSummary]
    events: list[SafetyEvent] = Field(default_factory=list)
    timeline: list[ComplianceSnapshot] = Field(default_factory=list)
    session_started_at: datetime | None = None
    session_ended_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    user: UserPublic


class SessionCreate(BaseModel):
    mode: SessionMode = SessionMode.individual
    additional_ppe: list[str] = Field(default_factory=list)


class SessionEnd(BaseModel):
    reason: str | None = None


class FrameDetection(BaseModel):
    class_name: str
    confidence: float
    box: list[float]
    track_id: str | None = None
    ppe_code: str | None = None
    evidence: int | None = None


class FrameResult(BaseModel):
    frame_id: str
    image_width: int
    image_height: int
    detections: list[FrameDetection]
    tracks: list[dict[str, Any]]
    machine_locked: bool
    inference_ms: float
    processing_ms: float
    server_total_ms: float
    server_sent_at_ms: float


