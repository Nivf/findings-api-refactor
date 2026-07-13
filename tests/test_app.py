"""API-level tests: exercise the real Flask app through its test client,
proving create_app's decorator-based parsing wiring actually works end to
end -- not just that the service/parser work in isolation."""

import pytest

from app import create_app
from request_parser import FindingsRequestParser
from service.findings_service import FindingsService
from store.findings_store import FindingsPage
from tests.test_findings_service import FakeFinding, FakeFindingsStore, make_summary


@pytest.fixture
def client():
    store = FakeFindingsStore(
        page=FindingsPage(items=[make_summary()], total_count=1),
        findings=[FakeFinding("f1", "pending")],
    )
    service = FindingsService(store)
    app = create_app(service, FindingsRequestParser())
    app.testing = True
    return app.test_client()


def test_get_findings_happy_path(client):
    response = client.get("/api/findings")

    assert response.status_code == 200
    assert response.get_json()["total_count"] == 1


def test_get_findings_rejects_invalid_delta_time(client):
    response = client.get("/api/findings?delta_time=abc")

    assert response.status_code == 400
    assert "delta_time" in response.get_json()["error"]


def test_patch_findings_happy_path(client):
    response = client.patch("/api/findings", json={"finding_ids": ["f1"], "status": "completed"})

    assert response.status_code == 200
    body = response.get_json()
    assert body["updated"] == ["f1"]
    assert body["failed"] == []


def test_patch_findings_rejects_missing_body(client):
    response = client.patch("/api/findings", json={})

    assert response.status_code == 400
