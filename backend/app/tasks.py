"""Worker tasks.

Core logic lives in a plain function (`process_job`) so it is easy to test
without a broker; the Celery task is a thin wrapper around it.
"""

import json
import logging

from app.celery_app import celery_app
from app.db import SessionLocal
from app.llm import get_provider
from app.models import JobStatus, AnalysisJob

logger = logging.getLogger(__name__)


def process_job(job_id: str, session_factory=SessionLocal) -> dict:
    """Run one analysis job end-to-end: load -> LLM -> persist result."""
    provider = get_provider()
    with session_factory() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            logger.warning("job %s not found", job_id)
            return {"id": job_id, "status": "not_found"}

        if job.status != JobStatus.PENDING.value:
            return {"id": job_id, "status": job.status}

        job.status = JobStatus.RUNNING.value
        db.commit()

        try:
            result = provider.analyze(job.input_text)
        except Exception as exc:  # noqa: BLE001 - any provider failure fails the job
            logger.exception("job %s failed", job_id)
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:500]
            db.commit()
            return {"id": job_id, "status": job.status, "error": job.error}

        job.status = JobStatus.COMPLETED.value
        job.summary = result.summary
        job.sentiment = result.sentiment
        job.themes = result.themes
        job.prompt_tokens = result.prompt_tokens
        job.completion_tokens = result.completion_tokens
        job.latency_ms = result.latency_ms
        db.commit()
        logger.info("job %s completed: %s", job_id, json.dumps({"sentiment": result.sentiment}))
        return {"id": job_id, "status": job.status}


@celery_app.task(name="tasks.run_analysis", bind=True, max_retries=3, default_retry_delay=10)
def run_analysis_task(self, job_id: str):  # type: ignore[no-untyped-def]
    try:
        return process_job(job_id)
    except Exception as exc:  # transient infra errors (DB/Redis) -> retry
        raise self.retry(exc=exc)
