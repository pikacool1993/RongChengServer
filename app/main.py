import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .env import load_env
from .database import engine
from .logging_config import init_logging
from .models import Base, ensure_schema_columns
from .admin import router as admin_router
from .response import fail, invalid_encrypted_request
from .routers import auth_router, match_router, task_router
from .routers.admin_ui import install_session_middleware, router as admin_ui_router
from .routers.order_query_ui import router as order_query_ui_router
from .routers.v2_admin import router as v2_admin_router
from .routers.v2_client import router as v2_client_router
from .v2_response import v2_error
from .v2_encrypted import (
    V2ClientError,
    V2InvalidEncryptedRequest,
    V2PayloadValidationError,
    encrypted_v2_body,
)

load_env()
init_logging()

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
ensure_schema_columns(engine)

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.include_router(admin_router)
app.include_router(match_router)
app.include_router(auth_router)
app.include_router(task_router)
app.include_router(v2_client_router)
app.include_router(v2_admin_router)
app.include_router(admin_ui_router)
app.include_router(order_query_ui_router)

install_session_middleware(app)


def _is_v2_client_path(path: str) -> bool:
    return path.startswith("/v2/") and not path.startswith("/v2/admin/")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("请求参数校验失败", exc_info=exc)
    if _is_v2_client_path(request.url.path):
        return JSONResponse(status_code=400, content=invalid_encrypted_request())
    if request.url.path.startswith("/v2/"):
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return v2_error(422, -422, "invalid request", {"errors": errors})
    return JSONResponse(
        status_code=422,
        content=fail(-200, msg=str(exc))
    )


@app.exception_handler(V2InvalidEncryptedRequest)
async def invalid_v2_encrypted_request_handler(request: Request, exc: V2InvalidEncryptedRequest):
    return JSONResponse(status_code=400, content=invalid_encrypted_request())


@app.exception_handler(V2PayloadValidationError)
async def invalid_v2_payload_handler(request: Request, exc: V2PayloadValidationError):
    return JSONResponse(
        status_code=422,
        content=encrypted_v2_body(-422, "invalid request", {"errors": exc.errors}),
    )


@app.exception_handler(V2ClientError)
async def v2_client_error_handler(request: Request, exc: V2ClientError):
    return JSONResponse(
        status_code=exc.status_code,
        content=encrypted_v2_body(exc.code, exc.msg),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if _is_v2_client_path(request.url.path):
        return JSONResponse(
            status_code=exc.status_code,
            content=encrypted_v2_body(-exc.status_code, str(exc.detail)),
            headers=exc.headers,
        )
    if not request.url.path.startswith("/v2/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    code_by_status = {
        400: -400,
        401: -401,
        403: -403,
        404: -404,
        409: -409,
        422: -422,
        500: -500,
        502: -502,
        503: -503,
    }
    return v2_error(
        exc.status_code,
        code_by_status.get(exc.status_code, -1),
        str(exc.detail),
        headers=exc.headers,
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("未捕获异常", exc_info=exc)
    if _is_v2_client_path(request.url.path):
        return JSONResponse(status_code=500, content=encrypted_v2_body(-500, "internal server error"))
    if request.url.path.startswith("/v2/"):
        return v2_error(500, -500, "internal server error")
    return JSONResponse(
        status_code=500,
        content=fail(-100, msg=str(exc))
    )
