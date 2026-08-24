import os
import tempfile

import pytest
from fastapi.testclient import TestClient


def test_app_boots_and_status_works(tmp_path):
    """Smoke: aplikacja startuje, seed zrodel dziala, /api/v1/status odpowiada."""
    os.environ["AIRALERT_DATABASE_URL"] = f"sqlite:///{tmp_path}/smoke.db"
    os.environ["AIRALERT_ADMIN_API_TOKEN"] = ""
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:  # context manager => odpala startup (create_all + seed)
        r = client.get("/api/v1/status")
        assert r.status_code == 200
        data = r.json()
        assert data["global_level"] == "green"
        assert any(s["slug"] == "rcb" for s in data["sources_health"])
        # pusty token admina => panel administracyjny wylaczony
        assert client.get("/admin-api/sources").status_code == 503

    r2 = TestClient(app).get("/api/v1/events")
    assert r2.status_code == 200
    get_settings.cache_clear()
