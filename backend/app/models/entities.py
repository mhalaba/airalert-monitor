"""Modele ORM. Geometrie PostGIS dodawane migracja na produkcji (kolumna event_locations.geom)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JSONVariant = JSONB().with_variant(SQLITE_JSON(), "sqlite")


def _uuid() -> str:
    return str(uuid.uuid4())


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)  # official_government|official_military|...
    country: Mapped[str] = mapped_column(String(2), default="PL")
    url: Mapped[str] = mapped_column(Text)
    ingest_kind: Mapped[str] = mapped_column(Text, default="rss")  # rss|html|manual|webhook
    trust_tier: Mapped[int] = mapped_column(Integer)  # 1..5 (1 najwyzszy)
    requires_manual_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_interval_s: Mapped[int] = mapped_column(Integer, default=120)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=30)
    domain_pin: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class RawMessage(Base):
    __tablename__ = "raw_messages"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_raw_source_external"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))
    content_hash: Mapped[str] = mapped_column(String(64))
    raw_payload: Mapped[dict] = mapped_column(JSONVariant)
    ingest_status: Mapped[str] = mapped_column(Text, default="new")
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Event(Base):
    """Zdarzenie w modelu kanonicznym (zgodnym ze specyfikacja projektu)."""

    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(Text, default="unknown")
    severity: Mapped[str] = mapped_column(Text, default="informational")
    urgency: Mapped[str] = mapped_column(Text, default="routine")
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    verification_status: Mapped[str] = mapped_column(Text, default="unverified")
    language: Mapped[str] = mapped_column(String(8), default="pl")
    title: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    alert_level: Mapped[str] = mapped_column(Text, default="green")
    alert_level_basis: Mapped[list] = mapped_column(JSONVariant, default=list)
    confidence_breakdown: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    status: Mapped[str] = mapped_column(Text, default="active")
    dedup_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    red_requires_operator: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    last_change_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )


class EventLocation(Base):
    __tablename__ = "event_locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(8), default="PL")
    voivodeship: Mapped[str | None] = mapped_column(Text, nullable=True)
    powiat: Mapped[str | None] = mapped_column(Text, nullable=True)
    precision: Mapped[str] = mapped_column(Text, default="region")


class EventSourceLink(Base):
    __tablename__ = "event_sources"
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    raw_message_id: Mapped[str] = mapped_column(ForeignKey("raw_messages.id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, default="primary")  # primary|corroborating|conflicting|retraction
    source_name: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(Text, default="unverified")
    source_country: Mapped[str] = mapped_column(String(8), default="PL")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trust_tier: Mapped[int] = mapped_column(Integer, default=5)


class StatusHistory(Base):
    __tablename__ = "status_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(Text)  # event|global
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    old_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text, default="system")
    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    platform: Mapped[str] = mapped_column(Text)
    voivodeships: Mapped[list] = mapped_column(JSONVariant, default=list)
    min_level: Mapped[str] = mapped_column(Text, default="orange")
    official_only: Mapped[bool] = mapped_column(Boolean, default=True)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(8), default="pl")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )


class NotificationLog(Base):
    """Rejestr wysylek - kontrola limitow, scalania i audytu falszywych alarmow."""

    __tablename__ = "notification_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("push_subscriptions.id"), index=True)
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sent_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    style: Mapped[str] = mapped_column(Text, default="silent")  # silent | loud
    merge_window_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)


class UserReport(Base):
    __tablename__ = "user_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    category: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )


class GlobalState(Base):
    __tablename__ = "global_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    global_level: Mapped[str] = mapped_column(Text, default="green")
    level_basis: Mapped[list] = mapped_column(JSONVariant, default=list)
    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
