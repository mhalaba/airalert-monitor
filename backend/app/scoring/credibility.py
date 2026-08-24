"""Przejrzysty scoring wiarygodnosci.

FORMULA (jawna, audytowalna - breakdown zwracany razem ze score):

  base(tier)          : tier1=0.95, tier2=0.85, tier3=0.65, tier4=0.40, tier5=0.15
  + corroboration     : +0.10 za KAZDE niezalezne zrodlo (max +0.20),
                        tylko gdy zrodla sa rozne (slug) i zgodne co do typu zdarzenia
  + official_confirm  : +0.05 gdy verification_status == officially_confirmed
  - conflict_penalty  : -0.15 jesli istnieje zrodlo sprzeczne
  - vagueness_penalty : -0.10 gdy brak lokalizacji, czasu lub zrodla oryginalnego

WYNIK przyciety do [0, 1].

NIGDY nie podnosi score: emocjonalny jezyk, liczba udostepnien, liczba
obserwujacych kanal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TIER_BASE = {1: 0.95, 2: 0.85, 3: 0.65, 4: 0.40, 5: 0.15}


@dataclass
class ScoreInput:
    trust_tiers: list[int]              # tier kazdego zrodla popierajacego zdarzenie
    source_slugs: list[str]             # slug zrodel (do oceny niezaleznosci)
    agreeing_source_count: int = 1      # liczba NIEZALEZNYCH zgodnych zrodel
    has_conflicting_source: bool = False
    has_location: bool = False
    has_publish_time: bool = True
    has_original_link: bool = False
    officially_confirmed: bool = False


@dataclass
class ScoreBreakdown:
    confidence: float
    base: float
    corroboration_bonus: float
    official_confirmation_bonus: float
    conflict_penalty: float
    vagueness_penalty: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "confidence": round(self.confidence, 2),
            "base": self.base,
            "corroboration_bonus": self.corroboration_bonus,
            "official_confirmation_bonus": self.official_confirmation_bonus,
            "conflict_penalty": self.conflict_penalty,
            "vagueness_penalty": self.vagueness_penalty,
            "notes": self.notes,
        }


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_score(inp: ScoreInput) -> ScoreBreakdown:
    notes: list[str] = []
    tiers = inp.trust_tiers or [5]
    base = TIER_BASE.get(min(tiers), 0.15)
    notes.append(f"Baza z najwyższego tieru źródła ({min(tiers)}): {base:.2f}")

    independent_slugs = len(set(inp.source_slugs))
    corroborating = max(0, min(2, independent_slugs - 1)) * 0.10
    if corroborating:
        notes.append(f"Korelacja z {independent_slugs} niezależnych źródeł: +{corroborating:.2f}")

    official_bonus = 0.05 if inp.officially_confirmed else 0.0
    if official_bonus:
        notes.append("Oficjalne potwierdzenie instytucji: +0.05")

    conflict_pen = -0.15 if inp.has_conflicting_source else 0.0
    if conflict_pen:
        notes.append("Wykryto źródło sprzeczne: -0.15")

    vagueness = 0.0
    if not inp.has_location:
        vagueness -= 0.05
        notes.append("Brak lokalizacji w komunikacie: -0.05")
    if not inp.has_publish_time:
        vagueness -= 0.03
        notes.append("Brak czasu publikacji: -0.03")
    if not inp.has_original_link:
        vagueness -= 0.02
        notes.append("Brak linku do oryginału: -0.02")

    confidence = _clamp01(base + corroborating + official_bonus + conflict_pen + vagueness)
    return ScoreBreakdown(
        confidence=round(confidence, 2),
        base=base,
        corroboration_bonus=corroborating,
        official_confirmation_bonus=official_bonus,
        conflict_penalty=conflict_pen,
        vagueness_penalty=vagueness,
        notes=notes,
    )


def verification_status_for(
    *,
    source_type_max: str | None,
    independent_sources: int,
    officially_confirmed: bool,
) -> str:
    """Mapowanie na status weryfikacji.

    'single_source' nawet dla oficjalnego zrodla oznacza: potwierdzone przez JEDNO zrodlo.
    'officially_confirmed' zarezerwowane dla komunikatow instytucji panstwowych PL/UA/NATO.
    """
    if officially_confirmed and source_type_max in ("official_government", "official_military"):
        return "officially_confirmed"
    if independent_sources >= 2:
        return "corroborated"
    if independent_sources == 1:
        return "single_source"
    return "unverified"
