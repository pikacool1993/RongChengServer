import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .env import load_env
from .database import engine
from .logging_config import init_logging
from .models import Base, ensure_schema_columns
from .admin import router as admin_router
from .response import fail
from .routers import auth_router, match_router, task_router
from .routers.admin_ui import install_session_middleware, router as admin_ui_router
from .routers.order_query_ui import router as order_query_ui_router

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
app.include_router(admin_ui_router)
app.include_router(order_query_ui_router)

install_session_middleware(app)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("请求参数校验失败", exc_info=exc)
    return JSONResponse(
        status_code=422,
        content=fail(-200, msg=str(exc))
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("未捕获异常", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=fail(-100, msg=str(exc))
    )
