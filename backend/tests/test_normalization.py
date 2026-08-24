import datetime as dt

import pytest

from app.normalize.geo import detect_language, detect_locations
from app.normalize.pipeline import canonical_text, content_hash, similarity


def test_classifies_air_alert_pl():
    from app.normalize.event_type import classify

    c = classify("Ogłaszamy alert lotniczy na terenie województwa podlaskiego")
    assert c.event_type == "air_alert"
    assert "alert lotniczy" in c.matched_keywords


def test_unknown_when_no_keywords():
    from app.normalize.event_type import classify

    assert classify("Przypominamy o bezpieczeństwie podczas wakacji").event_type == "unknown"


def test_exercise_before_alert():
    from app.normalize.event_type import classify

    # "cwiczenia" + "alert lotniczy" -> cwiczenia maja priorytet (regula ostroznosci)
    c = classify("Ćwiczenia systemu: testowy alert lotniczy")
    assert c.event_type == "exercise"


def test_detect_language():
    assert detect_language("Повітряна тривога у Львівській області") == "uk"
    assert detect_language("Ostrzeżenie meteorologiczne dla województwa mazowieckiego") == "pl"


def test_detect_locations_pl_region_precision_only():
    locs = detect_locations("Incydent w przestrzeni powietrznej nad województwem lubelskim, okolice Zamościa")
    assert any(l.voivodeship == "lubelskie" and l.country == "PL" for l in locs)
    for l in locs:
        assert l.precision in ("region", "city", "approximate", "country")


def test_all_16_voivodeships_detectable():
    """Regresja: kazde wojewodztwo musi byc wykrywalne (brakowalo wielkopolskiego)."""
    samples = {
        "mazowieckie": "Warszawa",
        "malopolskie": "Kraków",
        "slaskie": "Katowice",
        "lubelskie": "Lublin i Zamość",
        "podlaskie": "Białystok, Podlasie",
        "podkarpackie": "Rzeszów i Przemyśl",
        "warminsko-mazurskie": "Olsztyn",
        "dolnoslaskie": "Wrocław i Legnica",
        "lubuskie": "Zielona Góra",
        "wielkopolskie": "Poznań",
        "kujawsko-pomorskie": "Bydgoszcz i Toruń",
        "lodzkie": "Łódź",
        "opolskie": "Opole",
        "swietokrzyskie": "Kielce",
        "pomorskie": "Gdańsk",
        "zachodniopomorskie": "Szczecin i Koszalin",
    }
    for voiv, marker in samples.items():
        hits = detect_locations(marker)
        assert any(h.voivodeship == voiv for h in hits), f"Brak detekcji: {voiv} ({marker})"


def test_canonical_and_dedup_hashes():
    a = content_hash("ALERT LOTNICZY! Woj. podlaskie.")
    b = content_hash("alert lotniczy woj podlaskie")
    assert a == b
    assert similarity(a, b) > 0.9


def test_similar_texts_high_similarity():
    t1 = "Wzlot myśliwców po wykryciu obiektu w przestrzeni powietrznej RP"
    t2 = "Wzlot mysliwcow po wykryciu obiektu w przestrzeni powietrznej RP."
    assert similarity(t1, t2) >= 0.82
