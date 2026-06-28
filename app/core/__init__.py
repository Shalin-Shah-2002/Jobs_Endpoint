"""Cross-cutting concerns: config, db, errors, security, pagination.

Note: keep this module's top-level imports free of services and repositories
to avoid circular imports. Import :class:`Container` directly from
``app.core.container`` and :class:`Base` from ``app.core.database``.
"""

from app.core.config import Settings, get_settings
from app.core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.pagination import CursorPage, decode_cursor, encode_cursor
from app.core.security import require_api_key

__all__ = [
    "Settings",
    "get_settings",
    "AppError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "UnauthorizedError",
    "ForbiddenError",
    "require_api_key",
    "CursorPage",
    "decode_cursor",
    "encode_cursor",
]
