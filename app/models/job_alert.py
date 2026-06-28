"""Models for job alerts and their execution history."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import PrimaryKeyConstraint

from app.core.database import Base


class JobAlert(Base):
    __tablename__ = "job_alerts"

    id = Column(String(36), primary_key=True)
    name = Column(String(120), nullable=False)
    q = Column(String(120), nullable=False)
    location = Column(String(120), nullable=True)
    remote = Column(Boolean, nullable=True)
    sources_json = Column(Text, nullable=False, default="[]")
    limit = Column(Integer, nullable=False, default=25)
    check_interval_minutes = Column(Integer, nullable=False, default=60)
    discord_webhook_url = Column(String(1024), nullable=True)
    slack_webhook_url = Column(String(1024), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_new_jobs_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class JobAlertExecution(Base):
    __tablename__ = "job_alert_executions"

    id = Column(String(36), primary_key=True)
    alert_id = Column(
        String(36), ForeignKey("job_alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id = Column(String(36), ForeignKey("search_runs.id"), nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, index=True)
    total_jobs_found = Column(Integer, nullable=False, default=0)
    new_jobs_count = Column(Integer, nullable=False, default=0)
    notified = Column(Boolean, nullable=False, default=False)
    discord_status = Column(String(20), nullable=True)
    slack_status = Column(String(20), nullable=True)
    error = Column(Text, nullable=True)


class JobAlertSeenJob(Base):
    __tablename__ = "job_alert_seen_jobs"
    __table_args__ = (PrimaryKeyConstraint("alert_id", "job_id"),)

    alert_id = Column(
        String(36), ForeignKey("job_alerts.id", ondelete="CASCADE"), nullable=False
    )
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    seen_at = Column(DateTime(timezone=True), nullable=False)
