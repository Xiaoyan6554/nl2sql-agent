import shutil

import pytest
from fastapi.testclient import TestClient

from nl2sql.api import app, capacity, settings_dependency
from nl2sql.config import Settings
from tests.conftest import FakeModel


@pytest.fixture
def client(database, tmp_path, monkeypatch):
    directory = tmp_path / "database/unit"
    directory.mkdir(parents=True)
    shutil.copyfile(database, directory / "unit.sqlite")
    settings = Settings(api_key="test-secret", spider_dir=tmp_path)
    app.dependency_overrides[settings_dependency] = lambda: settings
    model = FakeModel(["SELECT name FROM people"])
    monkeypatch.setattr("nl2sql.api.ChatModel", lambda _: model)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_api_question_sql_rows_and_trace(client):
    response = client.post(
        "/ask", json={"db_id": "unit", "question": "names", "mode": "baseline", "row_limit": 1}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None and len(body["rows"]) == 1
    assert "LIMIT 1" in body["sql"] and body["trace"]
    assert "test-secret" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"db_id": "../../etc", "question": "x"},
        {"db_id": "unit", "question": "   "},
        {"db_id": "unit", "question": "x" * 2001},
        {"db_id": "unit", "question": "x", "row_limit": 1001},
        {"db_id": "unit", "question": "x", "mode": "unsafe"},
    ],
)
def test_invalid_requests(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_database_endpoints_and_unknown_db(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/databases").json() == ["unit"]
    assert "people" in client.get("/schema/unit").json()
    assert client.get("/schema/missing").status_code == 404
    assert client.post("/ask", json={"db_id": "missing", "question": "x"}).status_code == 404


def test_capacity_and_host(client):
    assert capacity.acquire(False)
    assert capacity.acquire(False)
    try:
        assert client.post("/ask", json={"db_id": "unit", "question": "x"}).status_code == 429
    finally:
        capacity.release()
        capacity.release()
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
