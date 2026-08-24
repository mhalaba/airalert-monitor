"""Testy integracyjne dispatchu powiadomien (reguly, scalanie, limity, audyt wysylek)."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.core.crypto import decrypt_token, encrypt_token
from app.db import Base, make_engine, make_session_factory
from app.ingest.base import FetchedItem
from app.main import _seed_sources
from app.models.entities import Event, NotificationLog, PushSubscription, Source
from app.notifications.dispatch import dispatch_for_event
from app.services.event_service import ingest_message


@pytest.fixture()
def env():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    _seed_sources(engine)
    SF = make_session_factory(engine)
    db = SF()
    rcb = db.execute(select(Source).where(Source.slug == "rcb")).scalar_one()
    yield db, SF, rcb
    db.close()


def _add_sub(db, **kw):
    from app.core.config import get_settings

    defaults = dict(
        token_encrypted=encrypt_token("fcm-token-test-12345", get_settings().push_token_secret),
        platform="android",
        voivodeships=["MAZOWIECKIE"], min_level="orange", official_only=True, muted=False,
    )
    defaults.update(kw)
    sub = PushSubscription(**defaults)
    db.add(sub)
    db.commit()
    return sub


NOW = dt.datetime(2026, 8, 23, 17, 0, tzinfo=dt.timezone.utc)


def _official_alert(db, rcb, *, text="Zagrożenie w przestrzeni powietrznej - alert lotniczy dla województwa mazowieckiego.", ext="r-1"):
    return ingest_message(db, source_row=rcb, item=FetchedItem(
        external_id=ext, url="https://www.gov.pl/web/rcb/x", title="Alert lotniczy",
        text=text, published_at=NOW, raw_payload={},
    ))


def test_official_orange_sends_loud_and_logs(env):
    db, _, rcb = env
    sub = _add_sub(db)
    outcome = _official_alert(db, rcb)  # ingest sam wywoluje dispatch (auto)
    # jawny dispatch ponownie - okno czasowe inne niz auto => druga wysylka
    sent = dispatch_for_event(db, outcome.event_id, now=NOW)
    assert sent == 1
    rows = db.execute(select(NotificationLog)).scalars().all()
    ours = [r for r in rows if r.subscription_id == sub.id]
    assert ours, "brak logu wysylki"
    assert any(r.style == "loud" and r.event_id == outcome.event_id for r in ours)


def test_unofficial_blocked_when_official_only(env):
    """Reguła F1/F9: nieoficjalne źródło nie wywołuje powiadomienia przy official_only."""
    db, _, rcb = env
    _add_sub(db)  # official_only=True
    tg = db.execute(select(Source).where(Source.slug == "telegram-manual")).scalar_one()
    outcome = ingest_message(db, source_row=tg, item=FetchedItem(
        external_id="tg-1", url="https://t.me/ch/1", title="Rakiety!",
        text="Podobno rakiety nad Warszawą!!!", published_at=NOW, raw_payload={},
    ))
    ev = db.get(Event, outcome.event_id)
    ev.status = "active"  # symulacja zatwierdzenia przez operatora
    db.commit()
    assert dispatch_for_event(db, outcome.event_id, now=NOW) == 0


def test_merge_window_deduplicates(env):
    db, _, rcb = env
    _add_sub(db)
    o1 = _official_alert(db, rcb, ext="a")
    o2 = _official_alert(
        db, rcb,
        text="Alert lotniczy - zagrożenie w przestrzeni powietrznej nad województwem mazowieckim trwa.",
        ext="b",
    )
    s1 = dispatch_for_event(db, o1.event_id, now=NOW)
    s2 = dispatch_for_event(db, o2.event_id, now=NOW + dt.timedelta(minutes=2))
    assert s1 == 1 and s2 == 0  # to samo okno 5-min => scalone


def test_muted_never_notified(env):
    db, _, rcb = env
    _add_sub(db, muted=True)
    o = _official_alert(db, rcb)
    assert dispatch_for_event(db, o.event_id, now=NOW) == 0


def test_green_events_never_notified(env):
    db, _, rcb = env
    _add_sub(db, min_level="yellow")
    o = ingest_message(db, source_row=rcb, item=FetchedItem(
        external_id="w-1", url="https://www.gov.pl/web/rcb/w",
        title="Komunikat informacyjny", text="Zalecana ostrożność podczas burz w górach.",
        published_at=NOW, raw_payload={},
    ))
    assert dispatch_for_event(db, o.event_id, now=NOW) == 0


def test_token_encrypt_roundtrip():
    blob = encrypt_token("fcm-token-1234567890", "sekret")
    assert blob != b"fcm-token-1234567890"
    assert decrypt_token(blob, "sekret") == "fcm-token-1234567890"
