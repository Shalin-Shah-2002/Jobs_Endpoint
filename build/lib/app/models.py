from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.database import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_url", name="uq_jobs_source_url"),
        Index("ix_jobs_source_posted", "source", "posted_at"),
    )

    id = Column(String(36), primary_key=True)
    source = Column(String(50), nullable=False, index=True)
    source_job_id = Column(String(255), nullable=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=True, index=True)
    remote_type = Column(String(50), nullable=True, index=True)
    salary = Column(String(255), nullable=True)
    equity = Column(String(255), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    source_url = Column(String(1024), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    raw_json = Column(Text, nullable=True)


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


class SourceStatus(Base):
    __tablename__ = "source_statuses"

    source = Column(String(50), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    docs_url = Column(String(1024), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(100), nullable=True)
    last_error_message = Column(Text, nullable=True)

