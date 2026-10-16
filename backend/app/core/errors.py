"""Consistent JSON errors: {"error": {"code": ..., "message": ...}}."""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.retry_after = status_code, code, message, retry_after


def _body(code: str, message: str, **extra) -> dict:
    err = {"code": code, "message": message}
    err.update({k: v for k, v in extra.items() if v is not None})
    return {"error": err}


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else None
        return JSONResponse(_body(exc.code, exc.message, retry_after=exc.retry_after), exc.status_code, headers=headers)

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        return JSONResponse(_body(f"http_{exc.status_code}", str(exc.detail)), exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("validation_error", "Invalid request.", details=details), 422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(_body("internal_error", "Unexpected server error."), 500)
