"""Translate AppError → HTTPException at the FastAPI boundary."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
