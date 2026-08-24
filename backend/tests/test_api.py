"""Testy integracyjne API + pelnego cyklu ingestu (SQLite in-memory)."""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.ingest.base import FetchedItem
from app.main import _seed_sources, create_app
from app.services.event_service import ingest_message


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AIRALERT_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("AIRALERT_ADMIN_API_TOKEN", "test-admin-token")
    get_settings.cache_clear()

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    _seed_sources(engine)
    SessionFactory = make_session_factory(engine)

    app = create_app()
    from app.db import get_db

    def override_get_db():
        db = SessionFactory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), SessionFactory, engine
    get_settings.cache_clear()


def _src(SessionFactory, slug="rcb"):
    from sqlalchemy import select

    from app.models.entities import Source

    db = SessionFactory()
    try:
        return db.execute(select(Source).where(Source.slug == slug)).scalar_one(), db
    except Exception:
        db.close()
        raise


def test_full_cycle_official_alert_becomes_active(client):
    tc, SF, _ = client
    src, db = _src(SF)
    now = dt.datetime.now(dt.timezone.utc)
    outcome = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="rcb-1", url="https://www.gov.pl/web/rcb/alert1",
        title="Alert lotniczy", text="Zagrożenie w przestrzeni powietrznej - alert lotniczy dla województwa podlaskiego.",
        published_at=now, raw_payload={"x": 1},
    ))
    assert outcome.action == "created"
    ev = tc.get(f"/api/v1/events/{outcome.event_id}").json()
    assert ev["event_type"] == "air_alert"
    assert ev["status"] == "active"
    assert any(l["voivodeship"] == "podlaskie" for l in ev["locations"])
    assert ev["disclaimer"].startswith("Informacja OSINT")


def test_official_alert_is_scored_and_levelled_immediately(client):
    """Regresja autoflush: zdarzenie po ingestcie MUSI miec policzony score i poziom."""
    tc, SF, _ = client
    src, db = _src(SF)
    o = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="rcb-2", url="https://www.gov.pl/web/rcb/alert2",
        title="Alert lotniczy", text="Zagrożenie w przestrzeni powietrznej - alert lotniczy dla województwa mazowieckiego.",
        published_at=dt.datetime.now(dt.timezone.utc), raw_payload={},
    ))
    ev = tc.get(f"/api/v1/events/{o.event_id}").json()
    assert float(ev["confidence"]) >= 0.9, ev
    assert ev["verification_status"] == "officially_confirmed"
    # oficjalne potwierdzenie PL tier-1 + air_alert => CZERWONY zgodnie z regułą
    assert ev["alert_level"] == "red"
    assert any("tier-1" in b for b in ev["alert_level_basis"])
    assert ev["confidence_breakdown"]["base"] == 0.95


def test_duplicate_from_other_source_corroborates(client):
    tc, SF, _ = client
    src, db = _src(SF)
    now = dt.datetime.now(dt.timezone.utc)
    text = "Alert lotniczy dla województwa lubelskiego - zagrożenie w przestrzeni powietrznej."
    o1 = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="r1", url="https://gov.pl/a", title="Alert", text=text,
        published_at=now, raw_payload={}))
    mon, db2 = _src(SF, "mon")
    o2 = ingest_message(db2, source_row=mon, item=FetchedItem(
        external_id="m1", url="https://gov.pl/b", title="Alert MON", text=text,
        published_at=now, raw_payload={}))
    assert o2.action == "corroborated"
    ev = tc.get(f"/api/v1/events/{o1.event_id}").json()
    assert len(ev["sources"]) == 2
    assert ev["verification_status"] == "officially_confirmed"


def test_manual_telegram_requires_approval_and_stays_yellow_max(client):
    """Regula bezpieczenstwa: telegram => pending_review; nigdy RED."""
    tc, SF, engine = client
    token = {"Authorization": "Bearer test-admin-token"}
    r = tc.post("/admin-api/messages/manual", json={
        "url": "https://t.me/somechannel/123",
        "title": "WIELKI ATAK!!!",
        "text": "Podobno rakiety lecą na Warszawę!!! (doniesienia niepotwierdzone)",
        "source_slug": "telegram-manual",
    }, headers=token)
    assert r.status_code == 200, r.text
    event_id = r.json()["event_id"]
    # pending_review -> niewidoczne w liscie publicznej aktywnych
    listing = tc.get("/api/v1/events").json()
    assert all(e["id"] != event_id for e in listing["items"])
    approve = tc.post(f"/admin-api/events/{event_id}/approve", headers=token)
    assert approve.status_code == 200
    ev = tc.get(f"/api/v1/events/{event_id}").json()
    assert ev["alert_level"] != "red"
    assert ev["verification_status"] in ("single_source", "unverified")


def test_red_confirm_full_flow_with_justification_and_audit(client):
    """RED: wymaga uzasadnienia, trafia do status_history i dziennika audytu."""
    tc, SF, _ = client
    headers = {"Authorization": "Bearer test-admin-token"}
    src, db = _src(SF)
    now = dt.datetime.now(dt.timezone.utc)
    o = ingest_message(db, source_row=src, item=FetchedItem(
        external_id="rcb-red", url="https://www.gov.pl/web/rcb/red",
        title="Alert lotniczy", text="Zagrożenie w przestrzeni powietrznej - alert lotniczy dla województwa podlaskiego.",
        published_at=now, raw_payload={},
    ))
    # brak uzasadnienia => 422
    r_no = tc.post(f"/admin-api/events/{o.event_id}/red-confirm",
                   json={"justification": ""}, headers=headers)
    assert r_no.status_code == 422
    # z uzasadnieniem => RED + audyt
    r_ok = tc.post(f"/admin-api/events/{o.event_id}/red-confirm",
                   json={"justification": "Potwierdzone przez RCB komunikatem nr 42/2026"}, headers=headers)
    assert r_ok.status_code == 200
    assert tc.get(f"/api/v1/events/{o.event_id}").json()["alert_level"] == "red"
    audit_log = tc.get("/admin-api/audit", headers=headers).json()
    assert any(a["action"] == "red_confirm" and a["entity_id"] == o.event_id for a in audit_log)


def test_red_confirm_blocked_without_admin(client):
    tc, SF, _ = client
    r = tc.post("/admin-api/events/x/red-confirm", json={"justification": "test test test"})
    assert r.status_code == 401


def test_admin_blocked_without_token(client):
    tc, SF, _ = client
    assert tc.get("/admin-api/sources").status_code == 401


def test_admin_disabled_when_no_token_configured(client, monkeypatch):
    """Pusty token => panel administracyjny zablokowany (503)."""
    tc, SF, engine = client
    monkeypatch.delenv("AIRALERT_ADMIN_API_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        r = tc.get("/admin-api/sources")
        assert r.status_code == 503
    finally:
        get_settings.cache_clear()


def test_status_endpoint_shows_sources_and_disclaimer(client):
    tc, SF, _ = client
    s = tc.get("/api/v1/status").json()
    assert s["global_level"] == "green"
    assert len(s["sources_health"]) >= 10
    assert "RCB" in s["disclaimer"] or "oficjalny" in s["disclaimer"]


def test_user_report_anonymous_accepted(client):
    tc, SF, _ = client
    r = tc.post("/api/v1/reports", json={"category": "wrong_classification", "message": "To cwiczenia"})
    assert r.status_code == 202


def test_push_register_delete_roundtrip(client):
    tc, SF, _ = client
    r = tc.post("/api/v1/push/register", json={
        "token": "fcm-token-abc1234567890", "platform": "android",
        "voivodeships": ["PODLASKIE"], "min_level": "orange", "official_only": True,
    })
    assert r.status_code == 201
    sid = r.json()["subscription_id"]
    assert tc.delete(f"/api/v1/push/{sid}").status_code == 204
