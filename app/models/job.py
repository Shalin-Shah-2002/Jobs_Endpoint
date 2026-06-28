from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text, UniqueConstraint

from app.core.database import Base


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
