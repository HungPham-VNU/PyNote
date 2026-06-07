"""Chat endpoint surface tests.

The full ingest → embed → stream loop is exercised against docker-compose; here
we cover auth, validation, and OpenAPI mounting so a routing regression shows up
without spinning up Postgres.
"""

import pytest
from fastapi.testclient import TestClient

from pynote_api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


NB_ID = "00000000-0000-0000-0000-000000000001"


def test_chat_requires_auth(client: TestClient) -> None:
    resp = client.post(f"/api/v1/notebooks/{NB_ID}/chat", json={"message": "hi"})
    assert resp.status_code == 401


def test_chat_rejects_empty_message(client: TestClient) -> None:
    resp = client.post(
        f"/api/v1/notebooks/{NB_ID}/chat",
        headers={"X-Dev-User": "u1", "X-Dev-Org": "o1"},
        json={"message": ""},
    )
    assert resp.status_code == 422


def test_history_requires_auth(client: TestClient) -> None:
    tid = "00000000-0000-0000-0000-000000000002"
    resp = client.get(f"/api/v1/notebooks/{NB_ID}/threads/{tid}/history")
    assert resp.status_code == 401


def test_routes_mounted_in_openapi(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"].keys()
    assert "/api/v1/notebooks/{notebook_id}/chat" in paths
    assert "/api/v1/notebooks/{notebook_id}/threads/{thread_id}/history" in paths
    # Option A: summary endpoints mounted under the notebook
    assert "/api/v1/notebooks/{notebook_id}/summary" in paths


def test_summary_requires_auth(client: TestClient) -> None:
    resp = client.get(f"/api/v1/notebooks/{NB_ID}/summary")
    assert resp.status_code == 401
    resp = client.post(f"/api/v1/notebooks/{NB_ID}/summary")
    assert resp.status_code == 401
