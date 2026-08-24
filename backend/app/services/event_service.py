"""Serwis orkiestrujacy: fetch -> raw -> normalize -> dedup -> score -> publish.

Kazdy krok zapisuje processing_notes; zadna decyzja nie jest ukryta.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dedup.engine import ExistingEvent, match_against
from app.ingest.base import FetchedItem
from app.normalize.pipeline import normalize
from app.scoring.alert_level import LevelInput, decide_level
from app.scoring.credibility import ScoreInput, compute_score, verification_status_for

log = logging.getLogger("airalert.service")

_OFFICIAL_TYPES = ("official_government", "official_military")


@dataclass
class IngestOutcome:
    action: str  # created | corroborated | conflicting | retraction | duplicate | rejected
    event_id: str | None = None


def _to_aware(x: dt.datetime | None) -> dt.datetime:
    if x is None:
        return dt.datetime.now(dt.timezone.utc)
    if x.tzinfo is None:
        return x.replace(tzinfo=dt.timezone.utc)
    return x


def list_existing_events(db: Session, since: dt.datetime) -> list[ExistingEvent]:
    from app.models.entities import Event, EventLocation, EventSourceLink

    rows = db.execute(
        select(Event).where(
            Event.status.in_(["active", "pending_review"]),
            Event.published_at >= since,
        )
    ).scalars().all()
    out: list[ExistingEvent] = []
    for ev in rows:
        locs = db.execute(
            select(EventLocation.name).where(EventLocation.event_id == ev.id)
        ).scalars().all()
        slugs = db.execute(
            select(EventSourceLink.source_name).where(EventSourceLink.event_id == ev.id)
        ).scalars().all()
        out.append(ExistingEvent(
            id=ev.id,
            title=ev.title,
            text=ev.original_text,
            event_type=ev.event_type,
            published_at=_to_aware(ev.published_at),
            locations=[l.lower() for l in locs],
            source_slugs=list(slugs),
        ))
    return out


def ingest_message(db: Session, *, source_row, item: FetchedItem):
    """Pelny cykl dla jednego surowego komunikatu. Zwraca IngestOutcome."""
    from app.models.entities import (
        Event,
        EventLocation,
        EventSourceLink,
        RawMessage,
        StatusHistory,
    )

    now = dt.datetime.now(dt.timezone.utc)
    norm = normalize(
        source_slug=source_row.slug,
        source_name=source_row.name,
        source_type=source_row.source_type,
        source_url=item.url,
        trust_tier=source_row.trust_tier,
        external_id=item.external_id,
        raw_payload=item.raw_payload,
        title=item.title,
        text=item.text,
        published_at=_to_aware(item.published_at),
        fetched_at=now,
    )

    raw = RawMessage(
        source_id=source_row.id,
        external_id=item.external_id,
        url=item.url,
        published_at=norm.published_at,
        fetched_at=now,
        content_hash=norm.content_hash_,
        raw_payload=item.raw_payload,
    )
    db.add(raw)
    db.flush()

    # ---- deduplikacja wobec zdarzen z ostatnich 72h ----
    existing = list_existing_events(db, now - dt.timedelta(hours=72))
    match = match_against(
        new_title=norm.title,
        new_text=norm.original_text,
        new_hash=norm.content_hash_,
        new_type=norm.event_type,
        published_at=norm.published_at,
        source_slug=source_row.slug,
        existing=existing,
    )

    if match.kind == "duplicate":
        raw.ingest_status = "rejected"
        raw.reject_reason = "duplikat"
        db.commit()
        return IngestOutcome("duplicate", match.event_id)

    if match.kind in ("corroborating", "conflicting", "retraction") and match.event_id:
        ev = db.get(Event, match.event_id)

        if match.kind == "retraction":
            # BEZPIECZENSTWO: wycofac zdarzenie moze wylacznie zrodlo o tier
            # <= tier najlepszego zrodla zdarzenia albo to samo zrodlo.
            # Anonimowy Telegram NIE moze anulowac alertu RCB (scenariusz F6-attack).
            best_tier = min(
                (row[0] for row in db.execute(
                    select(EventSourceLink.trust_tier).where(EventSourceLink.event_id == ev.id)
                ).all()),
                default=5,
            )
            existing_slugs = {
                r[0] for r in db.execute(
                    select(EventSourceLink.source_name).where(EventSourceLink.event_id == ev.id)
                ).all()
            }
            if source_row.trust_tier > best_tier and source_row.slug not in existing_slugs:
                log.warning(
                    "Odrzucono probe retrakcji %s przez slabe zrodlo %s (tier %s > %s)",
                    ev.id, source_row.slug, source_row.trust_tier, best_tier,
                )
                raw.ingest_status = "rejected"
                raw.reject_reason = "retrakcja od zrodla o zbyt niskim zaufaniu"
                db.commit()
                return IngestOutcome("rejected", ev.id)

        role = {"corroborating": "corroborating", "conflicting": "conflicting",
                "retraction": "retraction"}[match.kind]
        db.add(EventSourceLink(
            event_id=ev.id, raw_message_id=raw.id, role=role,
            source_name=source_row.slug, source_type=source_row.source_type,
            source_country=source_row.country, source_url=item.url,
            published_at=norm.published_at, trust_tier=source_row.trust_tier,
        ))
        raw.ingest_status = "normalized"
        if match.kind == "retraction":
            old_level = ev.alert_level
            ev.status = "retracted"
            ev.alert_level = "green"
            db.add(StatusHistory(entity_type="event", entity_id=ev.id,
                                 old_level=old_level, new_level="green",
                                 reason="Źródło wycofało informację (retrakcja/korekta)."))
            db.commit()
            return IngestOutcome("retraction", ev.id)
        db.flush()  # autoflush=False: link musi byc widoczny dla rescore
        rescore_event(db, ev.id)
        db.commit()
        _dispatch_if_public(db, match.event_id)
        return IngestOutcome("corroborated" if match.kind == "corroborating" else match.kind, ev.id)

    # ---- nowe zdarzenie ----
    status = "pending_review" if source_row.requires_manual_approval else "active"
    ev = Event(
        title=norm.title,
        original_text=norm.original_text,
        language=norm.language,
        event_type=norm.event_type,
        published_at=norm.published_at,
        updated_at=now,
        dedup_key=norm.content_hash_,
        status=status,
    )
    db.add(ev)
    db.flush()
    for loc in norm.locations:
        db.add(EventLocation(
            event_id=ev.id, name=loc["name"], country=loc["country"],
            voivodeship=loc.get("voivodeship"), powiat=loc.get("powiat"),
            precision=loc.get("precision", "region"),
        ))
    db.add(EventSourceLink(
        event_id=ev.id, raw_message_id=raw.id, role="primary",
        source_name=source_row.slug, source_type=source_row.source_type,
        source_country=source_row.country, source_url=item.url,
        published_at=norm.published_at, trust_tier=source_row.trust_tier,
    ))
    raw.ingest_status = "normalized"
    db.flush()  # autoflush=False: lokalizacje+link musza byc widoczne dla rescore
    notes = norm.processing_notes + [f"matched_keywords={norm.matched_keywords}"]
    rescore_event(db, ev.id, extra_notes=notes)
    db.commit()
    _dispatch_if_public(db, ev.id)
    return IngestOutcome("created", ev.id)


def _dispatch_if_public(db: Session, event_id: str) -> None:
    """Powiadomienia tylko dla zdarzen juz publicznych (active); pending_review czeka na approve."""
    with contextlib.suppress(Exception):  # awaria dispatchu nie moze przerwac ingestu
        from app.notifications.dispatch import dispatch_for_event

        sent = dispatch_for_event(db, event_id)
        if sent:
            log.info("Wyslano %s powiadomien dla %s", sent, event_id)


def rescore_event(db: Session, event_id: str, extra_notes: list[str] | None = None) -> None:
    """Przelicza confidence, verification_status i poziom alertu na bazie wszystkich linkow."""
    from app.models.entities import Event, EventLocation, EventSourceLink, StatusHistory

    ev = db.get(Event, event_id)
    links = db.execute(
        select(EventSourceLink).where(EventSourceLink.event_id == event_id)
    ).scalars().all()
    if not links or ev is None:
        log.warning("rescore_event %s: brak linkow lub zdarzenia - pominieto", event_id)
        return

    supporting = [l for l in links if l.role in ("primary", "corroborating")]
    conflicting = any(l.role == "conflicting" for l in links)
    retracted = any(l.role == "retraction" for l in links)
    best = min(supporting, key=lambda l: l.trust_tier)  # najnizszy numer = najlepszy tier
    independent_sources = len({l.source_name for l in supporting})
    officially_confirmed = best.source_type in _OFFICIAL_TYPES

    has_location = bool(db.execute(
        select(EventLocation.id).where(EventLocation.event_id == event_id).limit(1)
    ).first())
    countries = [r[0] for r in db.execute(
        select(EventLocation.country).where(EventLocation.event_id == event_id)).all()]

    score = compute_score(ScoreInput(
        trust_tiers=[l.trust_tier for l in supporting],
        source_slugs=[l.source_name for l in supporting],
        agreeing_source_count=independent_sources,
        has_conflicting_source=conflicting,
        has_location=has_location,
        has_publish_time=True,
        has_original_link=any(l.source_url for l in links),
        officially_confirmed=officially_confirmed,
    ))

    vstatus = verification_status_for(
        source_type_max=best.source_type,
        independent_sources=independent_sources,
        officially_confirmed=officially_confirmed,
    )

    old_level = ev.alert_level
    decision = decide_level(LevelInput(
        event_type=ev.event_type,
        severity=_severity_from_score(score.confidence, ev.event_type),
        urgency="elevated" if ev.event_type in ("air_alert", "missile_activity") else "routine",
        confidence=score.confidence,
        verification_status=vstatus,
        best_source_type=best.source_type,
        best_source_country=best.source_country,
        locations_countries=countries,
        is_exercise=ev.event_type == "exercise",
        operator_confirmed_red=False,
    ))
    if retracted:
        decision = decide_level(LevelInput("unknown", "informational", "routine",
                                           0.0, "unverified", "unverified"))

    basis = decision.basis + (extra_notes or [])
    ev.confidence = score.confidence
    ev.confidence_breakdown = score.as_dict()
    ev.verification_status = vstatus
    ev.severity = _severity_from_level(decision.level)
    ev.urgency = "immediate" if decision.level == "red" else ("elevated" if decision.level == "orange" else "routine")
    ev.alert_level = decision.level
    ev.red_requires_operator = decision.red_requires_operator
    ev.alert_level_basis = basis
    ev.last_change_at = dt.datetime.now(dt.timezone.utc)

    if old_level != decision.level:
        db.add(StatusHistory(
            entity_type="event", entity_id=ev.id,
            old_level=old_level, new_level=decision.level,
            reason=" | ".join(basis)[:500],
        ))


def _severity_from_score(conf: float, event_type: str) -> str:
    if event_type in ("air_alert", "missile_activity") and conf >= 0.8:
        return "critical"
    if conf >= 0.6:
        return "high"
    if conf >= 0.4:
        return "moderate"
    if conf >= 0.2:
        return "low"
    return "informational"


def _severity_from_level(level: str) -> str:
    return {"green": "informational", "yellow": "moderate",
            "orange": "high", "red": "critical"}.get(level, "informational")
