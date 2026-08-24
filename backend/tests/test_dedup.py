import datetime as dt

from app.dedup.engine import ExistingEvent, is_retraction, match_against


NOW = dt.datetime(2026, 8, 23, 12, 0, tzinfo=dt.timezone.utc)


def _existing(**kw):
    defaults = dict(
        id="e1",
        title="Alert lotniczy w województwie podlaskim",
        text="Zagrożenie w przestrzeni powietrznej - alert lotniczy dla Podlasia.",
        event_type="air_alert",
        published_at=NOW - dt.timedelta(hours=1),
        locations=["podlaskie"],
        source_slugs=["rcb"],
    )
    defaults.update(kw)
    return ExistingEvent(**defaults)


def test_identical_text_is_corroborating_from_other_source():
    e = _existing()
    m = match_against(
        new_title=e.title,
        new_text=e.text,
        new_hash=None,
        new_type="air_alert",
        published_at=e.published_at,
        source_slug="mon",
        existing=[e],
    )
    assert m.kind == "corroborating"
    assert m.event_id == "e1"


def test_same_source_same_content_is_duplicate():
    e = _existing()
    m = match_against(
        new_title=e.title,
        new_text=e.text,
        new_hash=None,
        new_type="air_alert",
        published_at=e.published_at,
        source_slug="rcb",
        existing=[e],
    )
    assert m.kind == "duplicate"


def test_out_of_window_is_new_event():
    e = _existing(published_at=NOW - dt.timedelta(days=5))
    m = match_against(
        new_title="Inny komunikat o pogodzie",
        new_text="Prognoza pogody na weekend: słonecznie.",
        new_hash="x1",
        new_type="weather",
        published_at=NOW,
        source_slug="psp",
        existing=[e],
    )
    assert m.kind == "new"


def test_retraction_detected():
    assert is_retraction("Sprostowanie: wcześniejsza informacja o obiekcie nie potwierdziła się")
    assert not is_retraction("Alert lotniczy trwa")


def test_conflicting_type_flagged():
    e = _existing(event_type="explosion")
    m = match_against(
        new_title="Alert lotniczy - podobna treść do poprzedniego zdarzenia eksplozji",
        new_text="Zagrożenie w przestrzeni powietrznej - alert lotniczy dla Podlasia.",
        new_hash=None,
        new_type="air_alert",
        published_at=NOW - dt.timedelta(minutes=30),
        source_slug="mon",
        existing=[e],
    )
    assert m.kind == "conflicting"
