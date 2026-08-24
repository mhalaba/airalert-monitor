"""System powiadomien: limity, scalanie duplikatow, domyslne wyciszenie.

REGULY:
- glosne alarmy TYLKO dla komunikatow oficjalnych (official_government/military),
- nieoficjalne => zawsze 'silent' z tekstem "Niezweryfikowana informacja do sprawdzenia",
- okno scalajace: wiele zdarzen tego samego poziomu/wojewodztwa w oknie X s = jedno powiadomienie,
- token bucket na subskrypcje (ochrona przed lawina),
- pelne wyciszenie (muted) respektowane zawsze.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

NEUTRAL_TEXT = "Niezweryfikowana informacja do sprawdzenia"


@dataclass
class EventNotification:
    event_id: str
    alert_level: str
    voivodeships: list[str]
    is_official: bool
    title_hint: str


@dataclass
class SubscriptionPrefs:
    subscription_id: str
    voivodeships: list[str]
    min_level: str
    official_only: bool
    muted: bool


_LEVEL_ORDER = ["green", "yellow", "orange", "red"]


def should_notify(
    event: EventNotification,
    prefs: SubscriptionPrefs,
    *,
    now: dt.datetime | None = None,
) -> tuple[bool, str, str]:
    """Zwraca (wysylac?, styl, merge_window_key)."""
    if prefs.muted:
        return False, "silent", ""

    level_idx = _LEVEL_ORDER.index(event.alert_level)
    min_idx = _LEVEL_ORDER.index(prefs.min_level)
    if level_idx < max(min_idx, _LEVEL_ORDER.index("yellow")):
        return False, "silent", ""

    if prefs.official_only and not event.is_official:
        return False, "silent", ""

    overlap = set(v.upper() for v in prefs.voivodeships) & set(
        v.upper() for v in event.voivodeships
    )
    if prefs.voivodeships and not overlap:
        return False, "silent", ""

    # Glosny alarm tylko dla oficjalnych; nieoficjalne zawsze neutralnie i cicho.
    style = "loud" if (event.is_official and event.alert_level in ("orange", "red")) else "silent"

    now = now or dt.datetime.now(dt.timezone.utc)
    bucket = event.voivodeships[0].upper() if event.voivodeships else "*"
    merge_key = f"{bucket}:{event.alert_level}:{now.strftime('%Y%m%dT%H')}{now.minute // 5}"
    return True, style, merge_key


class TokenBucket:
    """Ochrona przed lawina powiadomien per subskrypcja."""

    def __init__(self, max_per_hour: int = 10):
        self.max_per_hour = max_per_hour
        self._events: dict[str, list[float]] = {}

    def allow(self, subscription_id: str, now: float | None = None) -> bool:
        now = now or dt.datetime.now(dt.timezone.utc).timestamp()
        lst = [t for t in self._events.get(subscription_id, []) if now - t <= 3600.0]
        if len(lst) >= self.max_per_hour:
            self._events[subscription_id] = lst
            return False
        lst.append(now)
        self._events[subscription_id] = lst
        return True


def render_notification(
    event: EventNotification, style: str, *, locale: str = "pl"
) -> dict:
    title = (
        f"[{event.alert_level.upper()}] {event.title_hint}"
        if style == "loud"
        else NEUTRAL_TEXT
    )
    body = {
        "level": event.alert_level,
        "confidence_required": True,
        "footer_pl": "Informacja OSINT. Nie zastępuje RCB ani służb. Zagrożenie: dzwoń 112.",
    }
    return {"title": title[:120], "body": body, "style": style}
