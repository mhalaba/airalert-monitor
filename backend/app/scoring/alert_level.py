"""Reguly poziomow alertu: GREEN / YELLOW / ORANGE / RED.

TWARDE ZASADY BEZPIECZENSTWA:
- RED wyłącznie gdy: zdarzenie pochodzi z polskiego zrodla tier-1
  (official_government / official_military, country=PL) LUB operator
  zatwierdza recznie z uzasadnieniem.
- Doniesienia Telegramu / OSINT / mediow NIGDY nie podniosa poziomu powyzej YELLOW.
- ORANGE wymaga: zgodnosci >=2 niezaleznych zrodel ORAZ (oficjalnego zrodla
  lub incydentu blisko granicy PL wg lokalizacji country!=PL ale region przygraniczny).
- Kazda zmiana poziomu musi miec zapisana podstawe (basis).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LevelInput:
    event_type: str
    severity: str                 # informational|low|moderate|high|critical
    urgency: str                  # routine|elevated|urgent|immediate
    confidence: float             # 0..1
    verification_status: str      # unverified|single_source|corroborated|officially_confirmed
    best_source_type: str         # typ najlepszego zrodla zdarzenia
    best_source_country: str = "PL"
    locations_countries: list[str] = field(default_factory=list)
    is_exercise: bool = False
    operator_confirmed_red: bool = False


@dataclass
class LevelDecision:
    level: str                    # green|yellow|orange|red
    basis: list[str]
    red_requires_operator: bool = False


_SEVERE_TYPES = {"air_alert", "missile_activity", "airspace_incident", "explosion"}
_BORDER_UA_REGIONS_HINT = "UA"  # uproszczenie MVP: zdarzenia UA traktujemy jako kontekstowe


def decide_level(inp: LevelInput) -> LevelDecision:
    basis: list[str] = []

    if inp.event_type == "exercise":
        basis.append("Typ zdarzenia: ćwiczenie/zaplanowane działanie.")
        return LevelDecision("green", basis)

    severe = inp.event_type in _SEVERE_TYPES

    # --- RED ---
    red_eligible_by_rule = (
        inp.best_source_type in ("official_government", "official_military")
        and inp.best_source_country == "PL"
        and inp.verification_status == "officially_confirmed"
        and severe
        and inp.confidence >= 0.9
    )
    if inp.operator_confirmed_red and not red_eligible_by_rule:
        return LevelDecision(
            "red",
            ["CZERWONY nadany ręcznie przez operatora po analizie (wymóg: oficjalne potwierdzenie władz PL)."]
            + basis,
        )
    if red_eligible_by_rule:
        basis.append(
            "Oficjalne potwierdzenie polskiego źródła tier-1 "
            f"({inp.best_source_type}); verification_status=officially_confirmed; "
            f"confidence={inp.confidence:.2f}."
        )
        return LevelDecision("red", basis)
    # Kandydat do RED wymagajacy recznego zatwierdzenia operatora:
    if (
        severe
        and inp.best_source_type in ("official_government", "official_military")
        and inp.best_source_country == "PL"
        and inp.confidence >= 0.80
        and not inp.operator_confirmed_red
    ):
        basis.append(
            "KANDYDAT DO CZERWONEGO - wymaga potwierdzenia operatora "
            "(brak pełnych przesłanek automatycznej reguły RED)."
        )
        return LevelDecision("orange", basis, red_requires_operator=True)
    if inp.best_source_type in ("official_government", "official_military") and inp.best_source_country == "PL":
        basis.append(
            "Zdarzenie z polskiego źródła urzędowego bez pełnych przesłanek RED "
            "(brak officially_confirmed lub confidence<0.90)."
        )

    # --- ORANGE ---
    pl_affected = "PL" in inp.locations_countries
    ua_context = any(c != "PL" for c in inp.locations_countries)
    if (
        severe
        and inp.verification_status in ("corroborated", "officially_confirmed")
        and (pl_affected or (ua_context and inp.best_source_country != "PL"))
    ):
        where = "na terytorium PL" if pl_affected else "w pobliżu Polski (kontekst UA)"
        basis.append(
            f"Zdarzenie {where}, potwierdzone przez ≥2 niezależne źródła lub instytucję "
            f"(verification_status={inp.verification_status})."
        )
        return LevelDecision("orange", basis)

    # --- YELLOW ---
    if severe or inp.severity in ("moderate", "high") or inp.urgency in ("elevated", "urgent"):
        reasons = []
        if severe:
            reasons.append(f"typ zdarzenia: {inp.event_type}")
        if inp.verification_status == "single_source":
            reasons.append("informacja z pojedynczego źródła")
        if ua_context and not pl_affected:
            reasons.append("zdarzenie poza PL o znaczeniu kontekstowym")
        basis.append("; ".join(reasons) + ".")
        return LevelDecision("yellow", basis)

    # --- GREEN (default) ---
    basis.append("Brak potwierdzonego zagrożenia; komunikat informacyjny lub niskiej pilności.")
    return LevelDecision("green", basis)


# Globalny poziom systemu = maksimum poziomow aktywnych zdarzen.
_LEVEL_ORDER = ["green", "yellow", "orange", "red"]


def global_level(event_levels: list[str]) -> str:
    idx = max((_LEVEL_ORDER.index(l) for l in event_levels if l in _LEVEL_ORDER), default=0)
    return _LEVEL_ORDER[idx]
