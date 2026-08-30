"""Worker tests: run process_job directly (no broker) against the test DB."""

from app import tasks
from app.models import JobStatus


def test_process_job_completes(make_job):
    job_id = make_job("support was slow but the agent was helpful")

    result = tasks.process_job(job_id)

    assert result["status"] == JobStatus.COMPLETED.value


def test_process_job_persists_result(make_job):
    from app.db import SessionLocal
    from app.models import AnalysisJob

    job_id = make_job("onboarding was confusing and the docs are outdated")

    tasks.process_job(job_id)

    with SessionLocal() as db:
        job = db.get(AnalysisJob, job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value
        assert job.sentiment in {"positive", "negative", "neutral"}
        assert job.prompt_tokens > 0
        assert isinstance(job.themes, list)
        assert job.latency_ms is not None


def test_process_job_skips_non_pending_jobs(make_job):
    from app.db import SessionLocal
    from app.models import AnalysisJob, JobStatus

    job_id = make_job("fine")
    with SessionLocal() as db:
        db.get(AnalysisJob, job_id).status = JobStatus.COMPLETED.value
        db.commit()

    tasks.process_job(job_id)  # must not overwrite the completed result

    with SessionLocal() as db:
        assert db.get(AnalysisJob, job_id).summary is None
