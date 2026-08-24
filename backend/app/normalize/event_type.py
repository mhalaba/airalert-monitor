"""Klasyfikacja typu zdarzenia na podstawie regul slownikowych (PL/UK/EN).

ZASADA: klasyfikator NIE tworzy nowych faktow - tylko przypisuje typ zdarzenia
na podstawie jawnych slow-kluczy z komunikatu. Niepewnosc => 'unknown'.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Kolejnosc ma znaczenie: bardziej specyficzne typy sprawdzamy najpierw.
_RULES: list[tuple[str, list[str]]] = [
    ("exercise", [
        "ćwiczenia", "zaplanowane działani", "trening systemu",
        "навчання", "планові заходи", "exercise", "planned training",
    ]),
    ("weather", [
        "burza", "wichura", "gradobici", "ostrzeżenie meteorologiczne", "hydrologiczne",
        "погод", "гроза", "штормов", "storm warning", "severe weather",
    ]),
    ("air_alert", [
        "alert lotniczy", "zagrożenie w przestrzeni powietrznej", "alarm lotniczy",
        "повітряна тривога", "повітряна небезпека", "air raid alert", "air alert",
    ]),
    ("airspace_incident", [
        "naruszenie przestrzeni powietrznej", "obiekt w przestrzeni powietrznej",
        "przestrzeń powietrzna rp", "incydent w przestrzeni",
        "порушення повітряного простору", "airspace violation", "airspace incident",
    ]),
    ("aircraft_scramble", [
        "wzlot myśliwców", "pare myśliwców", "podniesienie par", "dyspozycyjność par",
        "підйом винищувачів", "scramble", "fighter jets scrambled",
    ]),
    ("missile_activity", [
        "rakieta", "pocisk", "atak rakietowy", "manewrujące uzbrojenie",
        "ракета", "ракетн", " missile ", "missile threat", "ballistic",
    ]),
    ("drone_activity", [
        # drony mapujemy na missile_activity? Nie - to osobny sygnal; MVP: infrastructure_threat/missile_activity
        "dron", "uav", "szahed", "дрон", "shahed", "drone",
    ]),
    ("explosion", [
        "eksplozja", "wybuch",
        "вибух", "explosion", "blast",
    ]),
    ("infrastructure_threat", [
        "zagrożenie infrastruktury", "infrastruktura krytyczna", "sabotaż",
        "загроза інфраструктурі", "critical infrastructure", "sabotage",
    ]),
]

_DRONE_TO_EVENT = "infrastructure_threat"  # ostroznie: aktywnosc dronow bez potwierdzenia celu


@dataclass
class Classification:
    event_type: str
    matched_keywords: list[str] = field(default_factory=list)


def classify(text: str) -> Classification:
    t = f" {text.lower()} "
    for event_type, keywords in _RULES:
        hits = [k for k in keywords if k.lower() in t]
        if hits:
            if event_type == "drone_activity":
                return Classification(_DRONE_TO_EVENT, hits)
            return Classification(event_type, hits)
    return Classification("unknown", [])
