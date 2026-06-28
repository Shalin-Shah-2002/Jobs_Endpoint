"""Import all models so SQLAlchemy registers them on the metadata."""

from app.models.job import Job
from app.models.job_alert import JobAlert, JobAlertExecution, JobAlertSeenJob
from app.models.search_run import SearchRun, SearchRunJob
from app.models.source_status import SourceStatus
from app.models.webhook import WebhookDelivery, WebhookSubscription

__all__ = [
    "Job",
    "JobAlert",
    "JobAlertExecution",
    "JobAlertSeenJob",
    "SearchRun",
    "SearchRunJob",
    "SourceStatus",
    "WebhookSubscription",
    "WebhookDelivery",
]
