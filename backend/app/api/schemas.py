"""Kontrakty API (Pydantic v2)."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app import DISCLAIMER_ALERT_FOOTER, DISCLAIMER_SHORT


class LocationOut(BaseModel):
    name: str
    country: str
    voivodeship: Optional[str] = None
    powiat: Optional[str] = None
    precision: str = "region"


class SourceRefOut(BaseModel):
    source_name: str
    source_type: str
    source_url: Optional[str] = None
    published_at: Optional[dt.datetime] = None
    role: str = "primary"
    trust_tier: int = 5


class StatusChangeOut(BaseModel):
    old_level: Optional[str]
    new_level: Optional[str]
    reason: str
    actor: str
    changed_at: dt.datetime


class ConfidenceBreakdown(BaseModel):
    confidence: float
    base: float
    corroboration_bonus: float
    official_confirmation_bonus: float
    conflict_penalty: float
    vagueness_penalty: float
    notes: list[str]


class EventOut(BaseModel):
    id: str
    event_type: str
    severity: str
    urgency: str
    confidence: float
    verification_status: str
    language: str
    title: str
    original_text: str = Field(description="Kopia tresci zrodlowej (audyt).")
    published_at: dt.datetime
    updated_at: dt.datetime
    alert_level: str
    alert_level_basis: list[str]
    confidence_breakdown: dict = {}
    status: str
    locations: list[LocationOut] = []
    sources: list[SourceRefOut] = []
    status_history: list[StatusChangeOut] = []
    is_stale: bool = False
    disclaimer: str = DISCLAIMER_ALERT_FOOTER


class EventListOut(BaseModel):
    items: list[EventOut]
    total: int
    disclaimer: str = DISCLAIMER_SHORT


class SourceHealth(BaseModel):
    slug: str
    name: str
    status: str  # ok | degraded | down | disabled | stale
    last_success_at: Optional[dt.datetime] = None
    consecutive_failures: int = 0


class StatusOut(BaseModel):
    global_level: str
    level_basis: list[str]
    updated_at: dt.datetime
    data_age_minutes: Optional[int] = None
    no_fresh_data: bool = False
    sources_health: list[SourceHealth]
    disclaimer: str = DISCLAIMER_SHORT


class ReportIn(BaseModel):
    event_id: Optional[str] = None
    category: Literal["wrong_classification", "wrong_location", "stale", "other"] = "other"
    message: Optional[str] = Field(None, max_length=2000)


class PushRegisterIn(BaseModel):
    token: str = Field(min_length=10, max_length=4096)
    platform: Literal["android", "ios", "web"] = "android"
    voivodeships: list[str] = Field(default_factory=list, max_length=16)
    min_level: Literal["yellow", "orange", "red"] = "orange"
    official_only: bool = True

    @field_validator("voivodeships")
    @classmethod
    def _norm_voiv(cls, v: list[str]) -> list[str]:
        out = []
        for item in v:
            if not isinstance(item, str) or len(item) > 32:
                raise ValueError("nieprawidlowa nazwa wojewodztwa")
            out.append(item.upper())
        return out
