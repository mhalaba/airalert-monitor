from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None):
    url = database_url or os.environ.get("AIRALERT_DATABASE_URL", "sqlite:///./airalert.db")
    kwargs: dict = {}
    if url.startswith("sqlite"):
        import sqlite3

        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


_engine = None
_SessionLocal = None


def get_db():
    """Zaleznosc FastAPI."""
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = make_engine()
        _SessionLocal = make_session_factory(_engine)
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
