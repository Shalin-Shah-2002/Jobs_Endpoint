from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text

from app.core.database import Base


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
