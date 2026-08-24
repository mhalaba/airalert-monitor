"""Silnik deduplikacji i korelacji zdarzen.

Reguly:
- identyczny content_hash => duplikat (przedruk),
- similarity >= SIM_THRESHOLD w oknie czasowym + nakladanie lokalizacji/typu => korelacja,
- wykrywanie odwolania: frazy retrakcyjne => rola 'retraction',
- sprzecznosc: rozne typy zdarzen dla tego samego czasu/miejsca => flaga konfliktu.

ZASADA NIEZALEZNOSCI: dwa wpisy z tego samego zrodla nie licza sie jako
dwa niezalezne potwierdzenia.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.normalize.pipeline import canonical_text, content_hash, similarity

SIM_THRESHOLD = 0.82
TIME_WINDOW = dt.timedelta(hours=24)

RETRACTION_MARKERS = [
    "sprostowanie", "odwołujemy", "odwołano", "wycofujemy informację", "fałszywa informacja",
    "fake", "не підтверджується", "спростування", "retraction", "correction",
]


def is_retraction(text: str) -> bool:
    low = f" {canonical_text(text)} "
    return any(m in low for m in RETRACTION_MARKERS)


@dataclass
class ExistingEvent:
    id: str
    title: str
    text: str
    event_type: str
    published_at: dt.datetime
    locations: list[str]
    source_slugs: list[str]


@dataclass
class MatchResult:
    kind: str  # duplicate | corroborating | conflicting | retraction | new
    event_id: str | None = None
    reason: str = ""


def match_against(
    new_title: str,
    new_text: str,
    new_hash: str | None,
    new_type: str,
    published_at: dt.datetime,
    source_slug: str,
    existing: list[ExistingEvent],
) -> MatchResult:
    new_hash = new_hash or content_hash(f"{new_title}\n{new_text}")
    if is_retraction(f"{new_title} {new_text}"):
        # Retrakcja dolaczamy do zdarzenia o najwyzszym podobienstwie
        best, best_sim = None, 0.0
        for e in existing:
            s = similarity(new_text, e.text)
            if s > best_sim and abs((e.published_at - published_at).total_seconds()) <= TIME_WINDOW.total_seconds() * 3:
                best, best_sim = e, s
        if best and best_sim >= SIM_THRESHOLD - 0.1:
            return MatchResult("retraction", best.id, f"Fraza retrakcyjna; podobieństwo {best_sim:.2f}")

    for e in existing:
        if abs((e.published_at - published_at).total_seconds()) > TIME_WINDOW.total_seconds():
            continue
        same_hash = content_hash(f"{e.title}\n{e.text}") == new_hash
        sim = similarity(new_text, e.text)
        loc_overlap = bool(set(l.lower() for l in e.locations) & set(_loc_names(new_title + new_text)))
        type_match = e.event_type == new_type
        if same_hash or (sim >= SIM_THRESHOLD and (type_match or loc_overlap)):
            if source_slug in e.source_slugs and same_hash:
                return MatchResult("duplicate", e.id, "Identyczna treść z tego samego źródła")
            return MatchResult(
                "corroborating" if type_match else "conflicting",
                e.id,
                f"Podobieństwo {sim:.2f}; zgodny typ={type_match}",
            )
    return MatchResult("new")


def _loc_names(text: str) -> list[str]:
    from app.normalize.geo import detect_locations

    return [l.name.lower() for l in detect_locations(text)]
