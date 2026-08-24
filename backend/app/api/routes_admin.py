"""Endpointy administracyjne - OGRANICZONE.

Ochrona: bearer token (AIRALERT_ADMIN_API_TOKEN). Pusty token => 503 (blokada).
Produkcja: dodatkowo mTLS + IP allowlist na poziomie reverse proxy.
Kazda operacja zapisuje wpis w dzienniku audytu.
"""
from __future__ import annotations

import contextlib
import datetime as dt

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.entities import AuditLog, Event, EventSourceLink, RawMessage, Source, StatusHistory
from app.services.event_service import ingest_message

router = APIRouter(prefix="/admin-api", tags=["admin"])


def require_admin(
    authorization: str | None = Header(None),
) -> str:
    import secrets

    from app.core.config import get_settings

    token = get_settings().admin_api_token
    if not token:
        raise HTTPException(status_code=503, detail="Panel administracyjny wyłączony w tej instancji")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Brak uwierzytelnienia")
    if not secrets.compare_digest(authorization.removeprefix("Bearer ").strip(), token):
        raise HTTPException(status_code=403, detail="Nieautoryzowany dostęp")
    return "operator:api"


def audit(db: Session, actor: str, action: str, entity: str, entity_id: str | None,
          before=None, after=None):
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=entity_id,
                    before=before, after=after))


@router.get("/sources")
def list_sources(db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    rows = db.execute(select(Source)).scalars().all()
    return [
        {
            "slug": s.slug, "name": s.name, "source_type": s.source_type,
            "country": s.country, "trust_tier": s.trust_tier, "enabled": s.enabled,
            "requires_manual_approval": s.requires_manual_approval,
            "last_success_at": s.last_success_at, "last_failure_at": s.last_failure_at,
            "consecutive_failures": s.consecutive_failures, "last_error": s.last_error,
        }
        for s in rows
    ]


@router.patch("/sources/{slug}")
def update_source(slug: str, enabled: bool | None = None, trust_tier: int | None = None,
                  db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    src = db.execute(select(Source).where(Source.slug == slug)).scalar_one_or_none()
    if not src:
        raise HTTPException(404, "Nie znaleziono źródła")
    before = {"enabled": src.enabled, "trust_tier": src.trust_tier}
    if enabled is not None:
        src.enabled = enabled
    if trust_tier is not None and 1 <= trust_tier <= 5:
        src.trust_tier = trust_tier
    after = {"enabled": src.enabled, "trust_tier": src.trust_tier}
    audit(db, actor, "update_source", "source", slug, before, after)
    db.commit()
    return {"slug": slug, **after}


@router.post("/messages/manual")
def manual_message(payload: dict, request: Request,
                   db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    """Reczny ingest (np. Telegram): operator podaje URL i tresc; system audytuje."""
    url = payload.get("url") or ""
    text = payload.get("text") or ""
    title = payload.get("title") or text[:80]
    if not url or not text:
        raise HTTPException(422, "Wymagane pola: url, text")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "URL musi być http(s)")
    slug = payload.get("source_slug") or "telegram-manual"
    src = db.execute(select(Source).where(Source.slug == slug)).scalar_one_or_none()
    if not src or not src.enabled:
        raise HTTPException(404, f"Źródło '{slug}' nie istnieje lub jest wyłączone")

    published_at = payload.get("published_at")
    pub_dt = (
        dt.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if isinstance(published_at, str)
        else dt.datetime.now(dt.timezone.utc)
    )
    from app.ingest.base import FetchedItem
    outcome = ingest_message(db, source_row=src, item=FetchedItem(
        external_id=payload.get("external_id") or url,
        url=url, title=title, text=text,
        published_at=pub_dt, raw_payload={"manual_entry_by": actor, **payload},
    ))
    audit(db, actor, "manual_ingest", "raw_message", None, None,
          {"url": url, "outcome": outcome.action, "event_id": outcome.event_id})
    db.commit()
    return outcome.__dict__


@router.post("/events/{event_id}/approve")
def approve_event(event_id: str, db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "Nie znaleziono zdarzenia")
    if ev.status != "pending_review":
        raise HTTPException(409, f"Zdarzenie ma status {ev.status}")
    before = {"status": ev.status}
    ev.status = "active"
    audit(db, actor, "approve_event", "event", event_id, before, {"status": "active"})
    db.commit()
    with contextlib.suppress(Exception):
        from app.notifications.dispatch import dispatch_for_event

        dispatch_for_event(db, event_id)
    return {"id": event_id, "status": "active"}


@router.post("/events/{event_id}/red-confirm")
def red_confirm(event_id: str, payload: dict, db: Session = Depends(get_db),
                actor: str = Depends(require_admin)):
    justification = (payload or {}).get("justification", "").strip()
    if len(justification) < 10:
        raise HTTPException(422, "Wymagane uzasadnienie (min. 10 znaków)")
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "Nie znaleziono zdarzenia")
    old = ev.alert_level
    links = db.execute(select(EventSourceLink).where(EventSourceLink.event_id == event_id)).scalars().all()
    pl_official = any(
        l.source_type in ("official_government", "official_military") and l.source_country == "PL"
        for l in links
    )
    if not pl_official:
        # RED bez polskiego zrodla urzedowego - tylko z pelnym uzasadnieniem operatora
        pass
    ev.alert_level = "red"
    ev.severity = "critical"
    ev.urgency = "immediate"
    ev.red_requires_operator = False
    basis = list(ev.alert_level_basis or []) + [
        f"CZERWONY nadany przez {actor}; uzasadnienie: {justification}"
    ]
    ev.alert_level_basis = basis
    db.add(StatusHistory(entity_type="event", entity_id=event_id, old_level=old,
                         new_level="red", reason=f"Operator: {justification}", actor=actor))
    audit(db, actor, "red_confirm", "event", event_id, {"level": old}, {"level": "red"})
    db.commit()
    return {"id": event_id, "alert_level": "red"}


@router.get("/audit")
def list_audit(from_: str | None = None, to: str | None = None, limit: int = 100,
               db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
    rows = db.execute(q).scalars().all()
    return [
        {"id": r.id, "at": r.at, "actor": r.actor, "action": r.action,
         "entity": r.entity, "entity_id": r.entity_id, "before": r.before, "after": r.after}
        for r in rows
    ]
