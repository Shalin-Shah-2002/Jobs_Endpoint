from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)


from app.core.database import Base


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        UniqueConstraint("source", "query", "location", name="uq_webhook_sub_unique"),
    )

    id = Column(String(36), primary_key=True)
    url = Column(String(1024), nullable=False)
    secret = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False, index=True)
    query = Column(String(120), nullable=False)
    location = Column(String(120), nullable=True)
    remote = Column(Boolean, nullable=True)
    poll_interval_seconds = Column(Integer, nullable=False, default=900)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    last_polled_at = Column(DateTime(timezone=True), nullable=True)
    last_delivered_at = Column(DateTime(timezone=True), nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(100), nullable=True)
    last_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "job_id", name="uq_webhook_delivery_unique"
        ),
    )

    id = Column(String(36), primary_key=True)
    subscription_id = Column(
        String(36), nullable=False, index=True
    )
    job_id = Column(String(36), nullable=False, index=True)
    delivered_at = Column(DateTime(timezone=True), nullable=False)
    status_code = Column(Integer, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    response_excerpt = Column(Text, nullable=True)
