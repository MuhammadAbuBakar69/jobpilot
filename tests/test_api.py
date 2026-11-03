import pytest
from fastapi.testclient import TestClient

from jobpilot.api import create_app

POSTING = (
    "Backend Developer at Sigma\nLocation: Remote\n"
    "Stack: Python, FastAPI\nhttps://sigma.example/jobs/9"
)


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path / "api.db"))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_then_list(client):
    created = client.post("/applications", json={"text": POSTING})
    assert created.status_code == 201
    body = created.json()
    assert body["company"] == "Sigma"
    assert body["role"].lower().startswith("backend")

    listed = client.get("/applications").json()
    assert len(listed) == 1


def test_duplicate_returns_conflict(client):
    assert client.post("/applications", json={"text": POSTING}).status_code == 201
    assert client.post("/applications", json={"text": POSTING}).status_code == 409


def test_status_update_and_validation(client):
    app_id = client.post("/applications", json={"text": POSTING}).json()["id"]
    assert client.patch(f"/applications/{app_id}", json={"status": "interview"}).status_code == 200
    assert client.patch(f"/applications/{app_id}", json={"status": "hired"}).status_code == 422
    assert client.patch("/applications/9999", json={"status": "offer"}).status_code == 404


def test_stats_endpoint(client):
    client.post("/applications", json={"text": POSTING})
    payload = client.get("/stats").json()
    assert payload["total"] == 1
    assert payload["by_status"]["applied"] == 1
