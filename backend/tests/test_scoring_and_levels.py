from app.scoring.alert_level import LevelInput, decide_level, global_level
from app.scoring.credibility import ScoreInput, compute_score


def test_official_pl_confirmed_is_red():
    d = decide_level(LevelInput(
        event_type="air_alert", severity="critical", urgency="immediate",
        confidence=0.95, verification_status="officially_confirmed",
        best_source_type="official_government", best_source_country="PL",
        locations_countries=["PL"],
    ))
    assert d.level == "red"
    assert any("tier-1" in b for b in d.basis)


def test_telegram_never_red():
    """TWARDA REGULA: doniesienia Telegramu nie moga ustawic RED."""
    d = decide_level(LevelInput(
        event_type="missile_activity", severity="critical", urgency="immediate",
        confidence=1.0, verification_status="corroborated",
        best_source_type="telegram", best_source_country="other",
        locations_countries=["PL"],
    ))
    assert d.level in ("orange", "yellow")
    assert d.level != "red"


def test_orange_requires_corroboration():
    d = decide_level(LevelInput(
        event_type="airspace_incident", severity="high", urgency="elevated",
        confidence=0.75, verification_status="corroborated",
        best_source_type="official_military", best_source_country="UA",
        locations_countries=["UA"],
    ))
    assert d.level == "orange"


def test_single_unverified_source_stays_yellow():
    d = decide_level(LevelInput(
        event_type="missile_activity", severity="high", urgency="urgent",
        confidence=0.4, verification_status="single_source",
        best_source_type="osint_channel", best_source_country="other",
        locations_countries=["UA"],
    ))
    assert d.level == "yellow"


def test_exercise_is_green():
    d = decide_level(LevelInput(
        event_type="exercise", severity="critical", urgency="immediate",
        confidence=0.99, verification_status="officially_confirmed",
        best_source_type="official_government", best_source_country="PL",
        locations_countries=["PL"], is_exercise=True,
    ))
    assert d.level == "green"


def test_red_candidate_requires_operator():
    d = decide_level(LevelInput(
        event_type="air_alert", severity="critical", urgency="immediate",
        confidence=0.85, verification_status="single_source",
        best_source_type="official_government", best_source_country="PL",
        locations_countries=["PL"],
    ))
    assert d.level == "orange"
    assert d.red_requires_operator is True


def test_global_level_takes_max():
    assert global_level(["green", "yellow"]) == "yellow"
    assert global_level(["green", "red", "yellow"]) == "red"
    assert global_level([]) == "green"


# ---------------- scoring wiarygodnosci ----------------

def test_official_single_source_high_score():
    s = compute_score(ScoreInput(
        trust_tiers=[1], source_slugs=["rcb"], agreeing_source_count=1,
        has_location=True, has_publish_time=True, has_original_link=True,
        officially_confirmed=True,
    ))
    assert s.confidence >= 0.95
    assert s.notes  # breakdown jawny


def test_anonymous_channel_low_score():
    s = compute_score(ScoreInput(
        trust_tiers=[5], source_slugs=["anon-tg"], agreeing_source_count=1,
        has_location=False, has_publish_time=False, has_original_link=False,
    ))
    assert s.confidence <= 0.15


def test_corroboration_increases_but_caps():
    s1 = compute_score(ScoreInput(trust_tiers=[4], source_slugs=["tg-a"]))
    s2 = compute_score(ScoreInput(trust_tiers=[4], source_slugs=["tg-a", "tg-b"]))
    s3 = compute_score(ScoreInput(trust_tiers=[4], source_slugs=["a", "b", "c", "d"]))
    assert s2.confidence > s1.confidence
    assert s3.corroboration_bonus <= 0.20 + 1e-9  # cap korelacji


def test_conflict_penalizes():
    base = ScoreInput(trust_tiers=[2], source_slugs=["psp"])
    with_conflict = ScoreInput(trust_tiers=[2], source_slugs=["psp"], has_conflicting_source=True)
    assert compute_score(with_conflict).confidence < compute_score(base).confidence
