"""Dispatch powiadomien: dopasowanie subskrypcji, reguly, scalanie, limity, wysylka.

Reguly bezpieczenstwa (patrz docs/04):
- glosne alarmy TYLKO dla zrodel oficjalnych i poziomow orange/red,
- nieoficjalne zawsze ciche z neutralnym tekstem,
- scalanie w oknie 5 min per (wojewodztwo, poziom),
- token bucket na subskrypcje,
- muted = nigdy.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_token
from app.models.entities import Event, EventLocation, EventSourceLink, NotificationLog, PushSubscription
from app.notifications.service import (
    EventNotification,
    SubscriptionPrefs,
    TokenBucket,
    render_notification,
    should_notify,
)

log = logging.getLogger("airalert.notify")

_OFFICIAL_TYPES = ("official_government", "official_military")

# MVP: procesowy bucket; produkcja: Redis (licznik wspoldzielony miedzy workerami).
_bucket = TokenBucket(max_per_hour=get_settings().notification_max_per_hour_per_subscription)


def _is_official_event(db: Session, event_id: str) -> bool:
    rows = db.execute(
        select(EventSourceLink.source_type).where(EventSourceLink.event_id == event_id)
    ).scalars().all()
    return any(t in _OFFICIAL_TYPES for t in rows)


def _voivodeships_of(db: Session, event_id: str) -> list[str]:
    rows = db.execute(
        select(EventLocation.voivodeship).where(EventLocation.event_id == event_id)
    ).scalars().all()
    return sorted({v.upper() for v in rows if v})


def dispatch_for_event(
    db: Session,
    event_id: str,
    *,
    now: dt.datetime | None = None,
) -> int:
    """Wysyla powiadomienia dla zdarzenia. Zwraca liczbe faktycznych wysylek."""
    ev = db.get(Event, event_id)
    if ev is None or ev.status != "active" or ev.alert_level == "green":
        return 0

    now = now or dt.datetime.now(dt.timezone.utc)
    settings = get_settings()
    event = EventNotification(
        event_id=ev.id,
        alert_level=ev.alert_level,
        voivodeships=_voivodeships_of(db, event_id),
        is_official=_is_official_event(db, event_id),
        title_hint=ev.title,
    )

    sent = 0
    subs = db.execute(
        select(PushSubscription).where(PushSubscription.muted.is_(False))
    ).scalars().all()
    for sub in subs:
        prefs = SubscriptionPrefs(
            subscription_id=sub.id,
            voivodeships=sub.voivodeships,
            min_level=sub.min_level,
            official_only=sub.official_only,
            muted=sub.muted,
        )
        ok, style, merge_key = should_notify(event, prefs, now=now)
        if not ok:
            continue

        # Scalanie: to samo okno 5-min => jedno powiadomienie
        already = db.execute(
            select(NotificationLog.id).where(
                NotificationLog.subscription_id == sub.id,
                NotificationLog.merge_window_key == merge_key,
            ).limit(1)
        ).first()
        if already:
            continue

        if not _bucket.allow(sub.id, now.timestamp()):
            log.info("Rate limit powiadomien dla %s - pomijam", sub.id)
            continue

        try:
            payload = render_notification(event, style, locale=sub.locale)
            _send(settings.fcm_server_key, sub, payload)
        except Exception:  # noqa: BLE001 - blad jednego tokena nie zatrzymuje reszty
            log.exception("Blad wysylki do subskrypcji %s", sub.id)
            continue

        db.add(NotificationLog(
            subscription_id=sub.id,
            event_id=event_id,
            style=style,
            merge_window_key=merge_key,
        ))
        sent += 1

    if sent:
        db.commit()
    return sent


def _send(fcm_server_key: str, sub: PushSubscription, payload: dict) -> None:
    """Wysylka. Bez skonfigurowanego klucza FCM tylko log (tryb suchy).

    Produkcja: FCM HTTP v1 (OAuth2 service account) / APNs token auth -
    punkt rozszerzenia, logika regul pozostaje niezmienna.
    """
    token = decrypt_token(sub.token_encrypted, get_settings().push_token_secret)[:8] + "..."
    if not fcm_server_key:
        log.info("[dry-run] push %s do %s (%s): %s",
                 payload["style"], sub.platform, token, payload["title"])
        return
    # TODO(produkcja): integracja FCM HTTP v1 + APNs; wymaga poświadczeń z menedżera sekretów.
    log.warning("FCM key ustawiony, ale integracja v1 wymaga konfiguracji - pomijam wysylke")
