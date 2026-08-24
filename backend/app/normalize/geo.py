"""Detekcja lokalizacji administracyjnych (wojewodztwa/powiaty) ze tekstu.

ZASADA BEZPIECZENSTWA: nie geokodujemy obiektow wojskowych ani infrastruktury
krytycznej. Precyzja maksymalnie do poziomu powiatu i TYLKO jesli wynika z tresci.

Dopasowanie jest odporne na brak diakrytykow ("Krakow" == "Kraków").
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


def _strip(s: str) -> str:
    """Lowercase + usuniecie diakrytykow (do dopasowan markerow)."""
    t = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in t if not unicodedata.combining(c))

VOIVODESHIPS = {
    "mazowieckie": ["mazowiecki", "mazowieckie", "warszaw"],
    "malopolskie": ["małopolski", "małopolskie", "krakow"],
    "slaskie": ["śląski", "śląskie", "katowic", "sosnowi"],
    "lubelskie": ["lubelski", "lubelskie", "lublin", "zamość", "bialski"],
    "podlaskie": ["podlaski", "białystok", "hajnowsk", "siematycze", "grajewsk", "podlasi"],
    "podkarpackie": ["podkarpacki", "podkarpackie", "rzeszow", "przemysl", "lubaczow", "jaroslaw", "bieszczad"],
    "warminsko-mazurskie": ["warmińsko", " warmiń", "mazurski", "olsztyn", "elbląg"],
    "dolnoslaskie": ["dolnośląski", "dolnośląskie", "wrocław", "legnic", "zgorzel"],
    "lubuskie": ["lubuski", "lubuskie", "zielonogór", "zielona g", "gorzów"],
    "wielkopolskie": ["wielkopolski", "wielkopolskie", "poznań", "pozan", "kalisz", "piła"],
    "kujawsko-pomorskie": ["kujawsko", "pomorski", "bydgoszcz", "toruni", "brodnica", "chełmno"],
    "lodzkie": ["łódzk", "łódź", "radomszczań", "piotrkow"],
    "opolskie": ["opolski", "opolskie", "opole"],
    "swietokrzyskie": ["świętokrzyski", "świętokrzyskie", "kielc"],
    "pomorskie": ["pomorskie", "gdańsk", "gdyni", "słupsk"],
    "zachodniopomorskie": ["zachodniopomorski", "szczecin", "koszalin", "świnoujść"],
}

# Miejsca przygraniczne UA czesto pojawiajace sie w komunikatach obwodow
UA_OBLASTS = {
    "wołyński": ["волинськ", "луцьк"],
    "lwowski": ["львівськ", "львов"],
}


def detect_language(text: str) -> str:
    pl_markers = ["ż", "ó", "ł", "ć", "ę", "ą", "ś", "ź", " i ", "oraz"]
    uk_markers = ["і", "ї", "є", " ґ", "про", "у ", "та "]
    pl_score = sum(text.lower().count(m) for m in pl_markers)
    uk_score = sum(text.lower().count(m) for m in uk_markers)
    if uk_score > pl_score:
        return "uk"
    if any(ch in text.lower() for ch in "żółćęąśź"):
        return "pl"
    if re_cyrillic(text):
        return "uk"
    return "en"


def re_cyrillic(text: str) -> bool:
    return sum(1 for ch in text if "\u0400" <= ch <= "\u04FF") > len(text) * 0.2


@dataclass
class LocationHit:
    name: str
    country: str
    voivodeship: str | None = None
    precision: str = "region"  # country|region|city|approximate


def detect_locations_pl(text: str) -> list[LocationHit]:
    """Zwraca trafienia wojewodztw. Precyzja 'region' - nigdy wiecej niz powiat."""
    low = _strip(text)
    hits: dict[str, LocationHit] = {}
    for voiv, markers in VOIVODESHIPS.items():
        for m in markers:
            if _strip(m) in low:
                hits[voiv] = LocationHit(name=voiv.capitalize(), country="PL", voivodeship=voiv, precision="region")
                break
    return list(hits.values())


def detect_locations_ua(text: str) -> list[LocationHit]:
    low = text.lower()
    low_strip = _strip(text)
    out: list[LocationHit] = []
    for obl, markers in UA_OBLASTS.items():
        if any(m in low or _strip(m) in low_strip for m in markers):
            out.append(LocationHit(name=obl.capitalize(), country="UA", precision="region"))
    if not out and re_cyrillic(text):
        out.append(LocationHit(name="Ukraina", country="UA", precision="country"))
    return out


def detect_locations(text: str) -> list[LocationHit]:
    return dedupe(detect_locations_pl(text) + detect_locations_ua(text))


def dedupe(locs: list[LocationHit]) -> list[LocationHit]:
    seen: set[tuple] = set()
    out = []
    for l in locs:
        key = (l.name, l.country)
        if key not in seen:
            seen.add(key)
            out.append(l)
    return out
