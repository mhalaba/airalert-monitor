"""Testy poprawek z audytu: retrakcja-atak, globalny poziom, walidacja wejscia."""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.ingest.base import FetchedItem
from app.main import _seed_sources
from app.services.event_service import ingest_message


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AIRALERT_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("AIRALERT_ADMIN_API_TOKEN", "test-admin-token")
    get_settings.cache_clear()
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    _seed_sources(engine)
    SF = make_session_factory(engine)

    from app.main import create_app

    app = create_app()
    from app.db import get_db

    def override():
        db = SF()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app), SF
    get_settings.cache_clear()


NOW = dt.datetime.now(dt.timezone.utc)
ALERT_TEXT = "Zagrożenie w przestrzeni powietrznej - alert lotniczy dla województwa podlaskiego."


def _rcb(SF):
    from sqlalchemy import select

    from app.models.entities import Source

    db = SF()
    return db.execute(select(Source).where(Source.slug == "rcb")).scalar_one(), db


def test_low_tier_source_cannot_retract_official_alert(client):
    """ATAK F6: anonimowy Telegram probuje 'sprostowac' alert RCB -> odrzucone."""
    tc, SF = client
    src, db = _rcb(SF)
    o = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="r1", url="https://gov.pl/a", title="Alert lotniczy",
        text=ALERT_TEXT, published_at=NOW, raw_payload={}))
    ev = tc.get(f"/api/v1/events/{o.event_id}").json()
    assert ev["status"] == "active"

    from sqlalchemy import select

    from app.models.entities import Source

    db2 = SF()
    tg = db2.execute(select(Source).where(Source.slug == "telegram-manual")).scalar_one()
    o2 = ingest_message(db2, source_row=tg, item=FetchedItem(
        external_id="t9", url="https://t.me/x/99", title="Sprostowanie",
        text="Sprostowanie: " + ALERT_TEXT + " Informacja nie potwierdziła się.",
        published_at=NOW, raw_payload={}))

    assert o2.action == "rejected"
    ev_after = tc.get(f"/api/v1/events/{o.event_id}").json()
    assert ev_after["status"] == "active"  # alert RCB nadal w mocy!
    assert ev_after["alert_level"] == "red"


def test_same_high_tier_source_can_retract(client):
    tc, SF = client
    src, db = _rcb(SF)
    o = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="r1", url="https://gov.pl/a", title="Alert lotniczy",
        text=ALERT_TEXT, published_at=NOW, raw_payload={}))
    o2 = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="r2", url="https://gov.pl/b", title="Odwołanie alertu",
        text="Odwołano alert lotniczy dla województwa podlaskiego. " + ALERT_TEXT,
        published_at=NOW + dt.timedelta(minutes=10), raw_payload={}))
    assert o2.action == "retraction"
    assert tc.get(f"/api/v1/events/{o.event_id}").json()["status"] == "retracted"


def test_global_level_reflects_active_events(client):
    tc, SF = client
    s = tc.get("/api/v1/status").json()
    assert s["global_level"] == "green"
    src, db = _rcb(SF)
    o = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="g1", url="https://gov.pl/g", title="Alert",
        text=ALERT_TEXT.replace("podlaskiego", "mazowieckiego"), published_at=NOW, raw_payload={}))
    s2 = tc.get("/api/v1/status").json()
    assert s2["global_level"] == "red"
    assert any("najwyższego aktywnego" in b or "najwyzszego aktywnego" in b for b in s2["level_basis"])


def test_report_invalid_category_422(client):
    tc, SF = client
    r = tc.post("/api/v1/reports", json={"category": "<script>x</script>", "message": "A" * 5000})
    assert r.status_code == 422


def test_push_register_validates_platform_and_level(client):
    tc, SF = client
    base = {"token": "fcm-token-abc123456", "voivodeships": ["podlaskie"]}
    ok = tc.post("/api/v1/push/register", json={**base, "platform": "ios", "min_level": "yellow"})
    assert ok.status_code == 201
    body = ok.json()
    sub_id = body["subscription_id"]
    # wojewodztwa znormalizowane do upper
    bad_platform = tc.post("/api/v1/push/register", json={**base, "platform": "symbian"})
    assert bad_platform.status_code == 422
    bad_level = tc.post("/api/v1/push/register", json={**base, "min_level": "green"})
    assert bad_level.status_code == 422
    assert tc.delete(f"/api/v1/push/{sub_id}").status_code == 204
