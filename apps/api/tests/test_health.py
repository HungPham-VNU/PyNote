"""API surface — exercised without a live DB.

readyz is intentionally not tested here because it hits Postgres; cover it
in integration tests once docker-compose is running.
"""

from fastapi.testclient import TestClient

from pynote_api.main import app


def test_healthz() -> None:
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_published_in_dev() -> None:
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    paths = spec["paths"].keys()
    assert "/api/v1/notebooks" in paths
    assert "/api/v1/notebooks/{notebook_id}" in paths


def test_notebooks_require_auth() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/notebooks")
    # Without X-Dev-User/X-Dev-Org headers in free/dev mode, expect 401.
    assert resp.status_code == 401
