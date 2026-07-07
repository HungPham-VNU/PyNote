"""Notebook CRUD surface tests (no DB needed).

Covers: route registration, auth gating, payload validation, and the LIKE
escaping used by title search. Live create/rename/delete flows run in the
integration suite once docker-compose is up (see README).
"""

import pytest
from fastapi.testclient import TestClient

from pynote_api.main import app
from pynote_api.routes.notebooks import escape_like

NB_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_openapi_lists_notebook_crud_routes(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "post" in paths["/api/v1/notebooks"]
    assert "get" in paths["/api/v1/notebooks"]
    assert "get" in paths["/api/v1/notebooks/{notebook_id}"]
    assert "patch" in paths["/api/v1/notebooks/{notebook_id}"]
    assert "delete" in paths["/api/v1/notebooks/{notebook_id}"]
    # Title search is a documented query param on the list route.
    list_params = {p["name"] for p in paths["/api/v1/notebooks"]["get"].get("parameters", [])}
    assert "q" in list_params


def test_list_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/notebooks").status_code == 401


def test_search_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/notebooks", params={"q": "physics"}).status_code == 401


def test_patch_requires_auth(client: TestClient) -> None:
    resp = client.patch(f"/api/v1/notebooks/{NB_ID}", json={"title": "new"})
    assert resp.status_code == 401


def test_delete_requires_auth(client: TestClient) -> None:
    assert client.delete(f"/api/v1/notebooks/{NB_ID}").status_code == 401


def test_patch_rejects_empty_title(client: TestClient) -> None:
    resp = client.patch(
        f"/api/v1/notebooks/{NB_ID}",
        headers={"X-Dev-User": "u1"},
        json={"title": ""},
    )
    # 422 short-circuits in validation before any DB access.
    assert resp.status_code == 422


def test_patch_rejects_overlong_title(client: TestClient) -> None:
    resp = client.patch(
        f"/api/v1/notebooks/{NB_ID}",
        headers={"X-Dev-User": "u1"},
        json={"title": "x" * 256},
    )
    assert resp.status_code == 422


def test_escape_like_neutralizes_wildcards() -> None:
    assert escape_like("100% notes") == "100\\% notes"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("back\\slash") == "back\\\\slash"
    assert escape_like("plain") == "plain"
