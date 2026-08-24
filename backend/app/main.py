"""Aplikacja FastAPI + seed zrodel + scheduler ingestu."""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app import DISCLAIMER_SHORT
from app.api import routes_admin, routes_public
from app.core.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.ingest.base import RateLimiter, check_domain, get_with_retry, parse_rss
from app.ingest.sources import SEEDS
from app.models.entities import Source
from app.services.event_service import ingest_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("airalert")

# Persistentne limity per zrodlo (per-wywolanie nie mialoby sensu)
_rate_limiters: dict[str, RateLimiter] = {}


def _seed_sources(engine) -> None:
    Session = make_session_factory(engine)
    db = Session()
    try:
        for seed in SEEDS:
            exists = db.execute(select(Source).where(Source.slug == seed.slug)).scalar_one_or_none()
            if not exists:
                db.add(Source(
                    slug=seed.slug, name=seed.name, source_type=seed.source_type,
                    country=seed.country, url=seed.url, ingest_kind=seed.ingest_kind,
                    trust_tier=seed.trust_tier,
                    requires_manual_approval=seed.requires_manual_approval,
                    fetch_interval_s=seed.fetch_interval_s,
                    domain_pin=seed.domain_pin or None,
                ))
        db.commit()
    finally:
        db.close()


def create_app() -> FastAPI:
    settings = get_settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):  # pragma: no cover - uruchamiane przy starcie serwera
        engine = make_engine(settings.database_url)
        Base.metadata.create_all(engine)
        _seed_sources(engine)
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Monitoring publicznych komunikatow i wskaznikow ryzyka. "
        + DISCLAIMER_SHORT,
        docs_url="/docs",
        lifespan=lifespan,
    )
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "Authorization"],
        )
    app.include_router(routes_public.router)
    app.include_router(routes_admin.router)
    return app


# ================= SCHEDULER (prosta petla asyncio - MVP) =================

async def fetch_source_once(source_row, session_factory) -> int:
    """Pojedynczy cykl pobrania dla zrodla rss/html. Zwraca liczbe przetworzonych wpisow."""
    if source_row.ingest_kind not in ("rss", "html"):
        return 0  # manual/webhook obslugiwane przez admina lub webhook endpoint
    limiter = _rate_limiters.setdefault(
        source_row.slug, RateLimiter(source_row.rate_limit_per_min)
    )
    await limiter.acquire()
    processed = 0
    async with httpx.AsyncClient(follow_redirects=True, headers={
        "User-Agent": "AirAlertMonitor/0.1 (+public-data-monitoring)"
    }) as client:
        try:
            resp = await get_with_retry(client, source_row.url)
            check_domain(str(resp.url), source_row.domain_pin or "")
            items = await parse_rss(resp.text) if source_row.ingest_kind == "rss" else []
            db = session_factory()
            try:
                for it in items:
                    try:
                        outcome = ingest_message(db, source_row=source_row, item=it)
                        processed += 1
                        log.info("%s: %s %s", source_row.slug, outcome.action, outcome.event_id)
                    except Exception:  # noqa: BLE001 - rollback, zeby kolejne wpisy zyly
                        log.exception("Blad normalizacji wpisu %s", it.external_id)
                        db.rollback()
                src = db.get(type(source_row), source_row.id)
                if src is not None:
                    src.last_success_at = dt.datetime.now(dt.timezone.utc)
                    src.consecutive_failures = 0
                db.commit()
            finally:
                db.close()
            return processed
        except Exception as exc:  # noqa: BLE001
            db = session_factory()
            try:
                src = db.get(type(source_row), source_row.id)
                if src is not None:
                    src.last_failure_at = dt.datetime.now(dt.timezone.utc)
                    src.last_error = str(exc)[:500]
                    src.consecutive_failures += 1
                db.commit()
            finally:
                db.close()
            log.error("Zrodlo %s niedostepne: %s", source_row.slug, exc)
            return processed


async def scheduler_loop(session_factory) -> None:  # pragma: no cover
    """Petla harmonogramu: co interwal per zrodlo (uproszczenie: wspolna tura co 60 s)."""
    while True:
        db = session_factory()
        try:
            sources = db.execute(
                select(Source).where(Source.enabled.is_(True))
            ).scalars().all()
        finally:
            db.close()
        for src in sources:
            now = dt.datetime.now(dt.timezone.utc).timestamp()
            last = src.last_success_at.timestamp() if src.last_success_at else 0
            if now - last >= src.fetch_interval_s:
                with contextlib.suppress(Exception):
                    await fetch_source_once(src, session_factory)
        await asyncio.sleep(60)


app = create_app()
