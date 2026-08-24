"""Rejestr zrodel (whitelist). Dodawanie zrodel WYLACZNIE przez migracje/admina.

Anti-spoofing: kazde zrodlo ma domain_pin - fetcher odrzuca tresc, ktora
przyszla z innej domeny niz oczekiwana.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSeed:
    slug: str
    name: str
    source_type: str  # official_government | official_military | verified_media | telegram | osint_channel
    country: str      # PL | UA | other
    url: str
    ingest_kind: str  # rss | html | manual | webhook
    trust_tier: int   # 1..5 (1 najwyzszy)
    requires_manual_approval: bool = False
    fetch_interval_s: int = 120
    domain_pin: str = ""


SEEDS: list[SourceSeed] = [
    # ===== POLSKA - tier 1 =====
    SourceSeed("rcb", "Rządowe Centrum Bezpieczeństwa", "official_government", "PL",
               "https://www.gov.pl/web/rcb/rss", "rss", 1, domain_pin="gov.pl"),
    SourceSeed("govpl-alerty", "gov.pl - alerty i komunikaty", "official_government", "PL",
               "https://www.gov.pl/web/obrona-narodowa", "html", 1, domain_pin="gov.pl"),
    SourceSeed("mon", "Ministerstwo Obrony Narodowej", "official_government", "PL",
               "https://www.gov.pl/web/obrona-narodowa", "html", 1, domain_pin="gov.pl"),
    SourceSeed("dorsz", "Dowództwo Operacyjne RSZ", "official_military", "PL",
               "https://www.dorsz.mil.pl/", "html", 1, requires_manual_approval=True,
               fetch_interval_s=60, domain_pin="mil.pl"),
    SourceSeed("dgrsz", "Dowództwo Generalne RSZ", "official_military", "PL",
               "https://www.generalnie.mil.pl/", "html", 1, domain_pin="mil.pl"),
    SourceSeed("psp", "Państwowa Straż Pożarna", "official_government", "PL",
               "https://www.gov.pl/web/psp", "html", 2, domain_pin="gov.pl"),
    SourceSeed("policja", "Policja", "official_government", "PL",
               "https://www.policja.gov.pl/", "html", 2, domain_pin="policja.gov.pl"),
    # ===== UKRAINA - tier 1/2 (komunikaty oficjalne) =====
    SourceSeed("ua-mod", "Міністерство оборони України", "official_military", "UA",
               "https://www.mil.gov.ua/en/news", "html", 2, requires_manual_approval=True,
               fetch_interval_s=180, domain_pin="mil.gov.ua"),
    SourceSeed("ua-dsns", "ДСНС України", "official_government", "UA",
               "https://dsns.gov.ua/", "html", 2, requires_manual_approval=True,
               fetch_interval_s=180, domain_pin="dsns.gov.ua"),
    # Air Alert UA: brak publicznego API -> integracja dopiero po umowie licencyjnej (docs/01 P2).
    # ===== NATO / EU =====
    SourceSeed("nato", "NATO Newsroom", "official_government", "other",
               "https://www.nato.int/cps/en/natohq/news.htm", "html", 2,
               fetch_interval_s=600, domain_pin="nato.int"),
    # ===== Kanaly Telegram - TYLKO reczne zatwierdzanie przez operatora =====
    SourceSeed("telegram-manual", "Telegram (wpisy zatwierdzane ręcznie)", "telegram", "other",
               "manual://telegram", "manual", 4, requires_manual_approval=True),
]
