"""Pipeline normalizacji: surowy komunikat -> model kanoniczny.

Nie modyfikuje tresci zrodlowej (original_text = kopia), dodaje wylacznie
metadane klasyfikacyjne i processing_notes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from app.normalize.event_type import classify
from app.normalize.geo import detect_language, detect_locations, LocationHit


def canonical_text(text: str) -> str:
    """Tekst do hashowania/deduplikacji: bez diakrytykow, interpunkcji, bialych znakow."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(canonical_text(text).encode()).hexdigest()


def simhash(text: str, bits: int = 64) -> int:
    """Prosty SimHash na 4-gramach znakowych kanonicznego tekstu."""
    tokens = canonical_text(text).replace(" ", "")
    grams = {tokens[i : i + 4] for i in range(max(0, len(tokens) - 3))}
    if not grams:
        return 0
    v = [0] * bits
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if v[i] > 0:
            out |= 1 << i
    return out


@dataclass
class NormalizedMessage:
    source_slug: str
    source_name: str
    source_type: str
    source_url: str | None
    trust_tier: int
    external_id: str
    raw_payload: dict
    published_at: dt.datetime
    fetched_at: dt.datetime

    language: str = "pl"
    title: str = ""
    original_text: str = ""
    event_type: str = "unknown"
    matched_keywords: list[str] = field(default_factory=list)
    locations: list[dict] = field(default_factory=list)
    content_hash_: str = ""
    processing_notes: list[str] = field(default_factory=list)


def normalize(
    *,
    source_slug: str,
    source_name: str,
    source_type: str,
    source_url: str | None,
    trust_tier: int,
    external_id: str,
    raw_payload: dict,
    title: str,
    text: str,
    published_at: dt.datetime,
    fetched_at: dt.datetime | None = None,
) -> NormalizedMessage:
    fetched_at = fetched_at or dt.datetime.now(dt.timezone.utc)
    cls = classify(f"{title} {text}")
    lang = detect_language(text)
    locs = detect_locations(text)
    notes: list[str] = []
    if cls.event_type == "unknown":
        notes.append("Nie rozpoznano typu zdarzenia - wymaga przegladu operatora.")
    if not locs:
        notes.append("Brak lokalizacji w tresci komunikatu.")
    return NormalizedMessage(
        source_slug=source_slug,
        source_name=source_name,
        source_type=source_type,
        source_url=source_url,
        trust_tier=trust_tier,
        external_id=external_id,
        raw_payload=raw_payload,
        published_at=published_at,
        fetched_at=fetched_at,
        language=lang,
        title=title.strip() or "(bez tytułu)",
        original_text=text,
        event_type=cls.event_type,
        matched_keywords=cls.matched_keywords[:10],
        locations=[asdict(l) for l in locs],
        content_hash_=content_hash(f"{title}\n{text}"),
        processing_notes=notes,
    )


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def similarity(a: str, b: str) -> float:
    """0..1 - 1 - odleglosc Hamminga SimHash / 64."""
    ha, hb = simhash(a), simhash(b)
    return 1.0 - hamming(ha, hb) / 64.0


__all__ = [
    "NormalizedMessage",
    "normalize",
    "canonical_text",
    "content_hash",
    "simhash",
    "similarity",
    "hamming",
    "LocationHit",
]
