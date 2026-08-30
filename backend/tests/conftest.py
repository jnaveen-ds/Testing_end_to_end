"""Test setup: scratch SQLite DB, no Redis/Celery broker required.

DATABASE_URL is set *before* importing app modules so the engine in
app.db points at the test database.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///./.pytest-feedback.db"
os.environ["LLM_PROVIDER"] = "fake"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine, SessionLocal
from app.main import app
from app.models import AnalysisJob


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    # Real get_db dependency works because DATABASE_URL points at the test DB.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_job():
    def _make(text: str = "great product, love it") -> str:
        with SessionLocal() as db:
            job = AnalysisJob(id="testjob123", input_text=text)
            db.add(job)
            db.commit()
            return job.id

    return _make
