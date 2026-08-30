"""API integration tests against a scratch SQLite DB (no broker needed for these paths)."""

from app import tasks
from app.models import JobStatus


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "provider": "fake"}


def test_create_and_get_job(client, monkeypatch):
    # POST enqueues a Celery task; replace the broker call with a no-op for this test.
    monkeypatch.setattr(tasks.run_analysis_task, "delay", lambda job_id: None)

    created = client.post("/analyses", json={"text": "great product, super fast"}).json()
    assert created["status"] == JobStatus.PENDING.value
    job_id = created["id"]

    fetched = client.get(f"/analyses/{job_id}").json()
    assert fetched["id"] == job_id
    assert fetched["input_text"] == "great product, super fast"


def test_get_missing_job_returns_404(client):
    assert client.get("/analyses/does-not-exist").status_code == 404


def test_rejects_blank_text(client):
    assert client.post("/analyses", json={"text": ""}).status_code == 422
