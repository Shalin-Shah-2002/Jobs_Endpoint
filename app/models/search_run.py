from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class SearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(String(36), primary_key=True)
    q = Column(String(120), nullable=False)
    location = Column(String(120), nullable=True)
    remote = Column(Boolean, nullable=True)
    sources_json = Column(Text, nullable=False)
    limit = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, index=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_jobs = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    errors_json = Column(Text, nullable=False, default="[]")


class SearchRunJob(Base):
    __tablename__ = "search_run_jobs"

    run_id = Column(String(36), ForeignKey("search_runs.id", ondelete="CASCADE"), primary_key=True)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    source = Column(String(50), nullable=False, index=True)
    attached_at = Column(DateTime(timezone=True), nullable=False)
