"""FastAPI application.

Endpoints:
  GET  /health          -> liveness probe (used later by deployments)
  POST /analyses        -> create a job and enqueue it on Redis
  GET  /analyses/{id}   -> poll job status + result
  GET  /analyses        -> recent jobs (for the UI list)
"""

import uuid

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.llm import get_provider
from app.models import AnalysisJob, JobStatus
from app.schemas import AnalysisCreate, JobOut
from app.tasks import run_analysis_task

settings = get_settings()

app = FastAPI(title="Feedback Analyzer API", version="0.1.0")

# The SPA may be served from a different origin (e.g. nginx container).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def create_tables() -> None:
    # Fine for learning; production-grade setups use Alembic migrations.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.llm_provider}


@app.post("/analyses", response_model=JobOut, status_code=201)
def create_analysis(payload: AnalysisCreate, db: Session = Depends(get_db)):
    job = AnalysisJob(id=uuid.uuid4().hex, input_text=payload.text)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Queue for the worker. .apply_async is the real production call;
    # in tests we can call process_job() directly without a broker.
    run_analysis_task.delay(job.id)
    return job


@app.get("/analyses/{job_id}", response_model=JobOut)
def get_analysis(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/analyses", response_model=list[JobOut])
def list_analyses(db: Session = Depends(get_db)):
    jobs = db.execute(
        select(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(20)
    ).scalars().all()
    return list(jobs)


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Tiny observability endpoint: job counts by status."""
    rows = db.execute(
        select(AnalysisJob.status, sqlfunc.count()).group_by(AnalysisJob.status)
    ).all()
    return {"provider": get_provider(settings).__class__.__name__, "jobs_by_status": {status: count for status, count in rows}}
