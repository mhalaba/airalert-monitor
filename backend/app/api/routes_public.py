"""Endpointy publiczne API v1 (tylko odczyt + zgloszenia + rejestracja push)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app import DISCLAIMER_SHORT, NO_DATA_MESSAGE
from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.api.schemas import (
    EventListOut,
    EventOut,
    LocationOut,
    PushRegisterIn,
    ReportIn,
    SourceHealth,
    SourceRefOut,
    StatusChangeOut,
    StatusOut,
)
from app.db import get_db
from app.models.entities import (
    Event,
    EventLocation,
    EventSourceLink,
    PushSubscription,
    Source,
    StatusHistory,
    UserReport,
)

router = APIRouter(prefix="/api/v1", tags=["public"])

_STALE_AFTER_MIN = 60


def _event_to_out(db: Session, ev: Event) -> EventOut:
    locs = db.execute(
        select(EventLocation).where(EventLocation.event_id == ev.id)
    ).scalars().all()
    links = db.execute(
        select(EventSourceLink).where(EventSourceLink.event_id == ev.id)
    ).scalars().all()
    hist = db.execute(
        select(StatusHistory)
        .where(StatusHistory.entity_type == "event", StatusHistory.entity_id == ev.id)
        .order_by(desc(StatusHistory.changed_at))
        .limit(20)
    ).scalars().all()

    now = dt.datetime.now(dt.timezone.utc)
    updated = _aware(ev.updated_at)
    is_stale = (now - updated) > dt.timedelta(minutes=_STALE_AFTER_MIN)

    return EventOut(
        id=ev.id,
        event_type=ev.event_type,
        severity=ev.severity,
        urgency=ev.urgency,
        confidence=float(ev.confidence),
        verification_status=ev.verification_status,
        language=ev.language,
        title=ev.title,
        original_text=ev.original_text,
        published_at=_aware(ev.published_at),
        updated_at=updated,
        alert_level=ev.alert_level,
        alert_level_basis=list(ev.alert_level_basis or []),
        confidence_breakdown=dict(ev.confidence_breakdown or {}),
        status=ev.status,
        locations=[LocationOut(**{
            "name": l.name, "country": l.country, "voivodeship": l.voivodeship,
            "powiat": l.powiat, "precision": l.precision,
        }) for l in locs],
        sources=[SourceRefOut(
            source_name=l.source_name, source_type=l.source_type, source_url=l.source_url,
            published_at=_aware(l.published_at) if l.published_at else None,
            role=l.role, trust_tier=l.trust_tier,
        ) for l in links],
        status_history=[StatusChangeOut(
            old_level=h.old_level, new_level=h.new_level, reason=h.reason,
            actor=h.actor, changed_at=_aware(h.changed_at),
        ) for h in hist],
        is_stale=is_stale,
    )


def _aware(x: dt.datetime) -> dt.datetime:
    if x.tzinfo is None:
        return x.replace(tzinfo=dt.timezone.utc)
    return x


_LEVEL_ORDER = ("green", "yellow", "orange", "red")


def _derive_global_level(db: Session) -> tuple[str, list[str]]:
    """Globalny poziom = maksimum poziomow aktywnych zdarzen (+ ich bazy)."""
    rows = db.execute(
        select(Event.alert_level, Event.title, Event.confidence).where(
            Event.status == "active", Event.alert_level != "green"
        )
    ).all()
    if not rows:
        return "green", ["Brak aktywnych zdarzen."]
    order = {l: i for i, l in enumerate(_LEVEL_ORDER)}
    top = max(rows, key=lambda r: order.get(r[0], 0))
    basis = [
        f"Poziom globalny wynika z najwyzszego aktywnego zdarzenia ({top[1]!r}, "
        f"poziom {top[0]}, pewność {float(top[2]):.2f})."
    ]
    return top[0], basis


@router.get("/status", response_model=StatusOut)
def get_status(db: Session = Depends(get_db)):
    sources = db.execute(select(Source)).scalars().all()
    now = dt.datetime.now(dt.timezone.utc)

    health: list[SourceHealth] = []
    freshest_success: dt.datetime | None = None
    for s in sources:
        if not s.enabled:
            health.append(SourceHealth(slug=s.slug, name=s.name, status="disabled",
                                       last_success_at=None, consecutive_failures=s.consecutive_failures))
            continue
        if s.last_failure_at and s.consecutive_failures >= 3:
            status = "down"
        elif s.last_failure_at and s.last_success_at and s.last_failure_at > s.last_success_at:
            status = "degraded"
        else:
            status = "ok"
            if s.last_success_at:
                t = _aware(s.last_success_at)
                freshest_success = max(freshest_success, t) if freshest_success else t
        health.append(SourceHealth(slug=s.slug, name=s.name, status=status,
                                   last_success_at=s.last_success_at,
                                   consecutive_failures=s.consecutive_failures))

    no_fresh = freshest_success is None or (now - freshest_success) > dt.timedelta(hours=6)
    level, basis = _derive_global_level(db)
    return StatusOut(
        global_level=level,
        level_basis=basis,
        updated_at=now,
        data_age_minutes=int((now - freshest_success).total_seconds() // 60) if freshest_success else None,
        no_fresh_data=no_fresh,
        sources_health=health,
        disclaimer=(NO_DATA_MESSAGE + " " + DISCLAIMER_SHORT) if no_fresh else DISCLAIMER_SHORT,
    )


@router.get("/events", response_model=EventListOut)
def list_events(
    level: str | None = Query(None, pattern="^(green|yellow|orange|red)$"),
    event_type: str | None = None,
    source_type: str | None = None,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    voivodeship: str | None = None,
    since: dt.datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = select(Event).where(Event.status.in_(["active", "resolved"]))
    if level:
        q = q.where(Event.alert_level == level)
    if event_type:
        q = q.where(Event.event_type == event_type)
    if min_confidence > 0:
        q = q.where(Event.confidence >= min_confidence)
    if since:
        q = q.where(Event.published_at >= since)
    if voivodeship:
        q = q.where(
            Event.id.in_(
                select(EventLocation.event_id).where(
                    func.lower(EventLocation.voivodeship) == voivodeship.lower()
                )
            )
        )
    if source_type:
        q = q.where(
            Event.id.in_(
                select(EventSourceLink.event_id).where(
                    EventSourceLink.source_type == source_type
                )
            )
        )
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(desc(Event.published_at)).limit(limit).offset(offset)).scalars().all()

    items = [_event_to_out(db, ev) for ev in rows]
    return EventListOut(items=items, total=total)


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: str, db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if not ev or ev.status in ("superseded",):
        raise HTTPException(status_code=404, detail="Nie znaleziono zdarzenia")
    return _event_to_out(db, ev)


@router.post("/reports", status_code=202)
def create_report(payload: ReportIn, db: Session = Depends(get_db)):
    """Zgloszenie bledu klasyfikacji - ANONIMOWE, bez danych osobowych."""
    rep = UserReport(event_id=payload.event_id, category=payload.category, message=payload.message)
    db.add(rep)
    db.commit()
    return {"id": rep.id}


@router.post("/push/register", status_code=201)
def register_push(payload: PushRegisterIn, db: Session = Depends(get_db)):
    settings = get_settings()
    sub = PushSubscription(
        token_encrypted=encrypt_token(payload.token, settings.push_token_secret),
        platform=payload.platform,
        voivodeships=[v.upper() for v in payload.voivodeships],
        min_level=payload.min_level,
        official_only=payload.official_only,
    )
    db.add(sub)
    db.commit()
    return {"subscription_id": sub.id}


@router.delete("/push/{subscription_id}", status_code=204)
def delete_push(subscription_id: str, db: Session = Depends(get_db)):
    sub = db.get(PushSubscription, subscription_id)
    if sub:
        db.delete(sub)
        db.commit()
