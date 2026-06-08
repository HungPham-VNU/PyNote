"""Source endpoint surface tests (no DB / no Redis / no S3 needed).

Covers: auth required, content-type validation. End-to-end upload → parse
runs in an integration suite once docker-compose is up (see README).
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pynote_api.deps import get_arq
from pynote_api.main import app

NB_ID = "00000000-0000-0000-0000-000000000001"


async def _fake_arq() -> AsyncIterator[Any]:
    class _NoopArq:
        async def enqueue_job(self, *_: object, **__: object) -> None:
            return None

    yield _NoopArq()


@pytest.fixture
def client() -> TestClient:
    # Replace the Redis-backed arq pool with a no-op so endpoint tests stay
    # independent of docker-compose.
    app.dependency_overrides[get_arq] = _fake_arq
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_arq, None)


def test_upload_requires_auth(client: TestClient) -> None:
    resp = client.post(
        f"/api/v1/notebooks/{NB_ID}/sources/upload",
        files={"file": ("x.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
    )
    assert resp.status_code == 401


def test_upload_rejects_non_pdf(client: TestClient) -> None:
    resp = client.post(
        f"/api/v1/notebooks/{NB_ID}/sources/upload",
        headers={"X-Dev-User": "u1", "X-Dev-Org": "o1"},
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    # 415 short-circuits before the notebook lookup (no DB hit needed).
    assert resp.status_code == 415


def test_openapi_lists_source_routes(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"].keys()
    assert "/api/v1/notebooks/{notebook_id}/sources" in paths
    assert "/api/v1/notebooks/{notebook_id}/sources/upload" in paths
    assert "/api/v1/sources/{source_id}" in paths
    assert "/api/v1/sources/{source_id}/file" in paths  # M5: PDF stream


def test_file_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/sources/00000000-0000-0000-0000-000000000099/file")
    assert resp.status_code == 401
