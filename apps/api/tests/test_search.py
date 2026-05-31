"""Search endpoint surface tests (no live embedder / DB).

The end-to-end "ingest → embed → search" loop runs in the integration suite
once docker-compose is up. Here we cover auth + OpenAPI shape so we know the
route is mounted and validated.
"""

import pytest
from fastapi.testclient import TestClient

from pynote_api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


NB_ID = "00000000-0000-0000-0000-000000000001"


def test_search_requires_auth(client: TestClient) -> None:
    resp = client.post(f"/api/v1/notebooks/{NB_ID}/search", json={"q": "hello"})
    assert resp.status_code == 401


def test_search_rejects_empty_query(client: TestClient) -> None:
    resp = client.post(
        f"/api/v1/notebooks/{NB_ID}/search",
        headers={"X-Dev-User": "u1", "X-Dev-Org": "o1"},
        json={"q": ""},
    )
    # Pydantic rejects min_length=1 with 422 before the route runs.
    assert resp.status_code == 422


def test_search_route_in_openapi(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert "/api/v1/notebooks/{notebook_id}/search" in spec["paths"]
