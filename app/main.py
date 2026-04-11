import json
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .env import load_env
from .database import engine
from .logging_config import init_logging
from .models import Base
from .admin import router as admin_router
from .response import fail
from .routers import auth_router, match_router, task_router
from .routers.admin_ui import install_session_middleware, router as admin_ui_router
from .sign import generate_sign

load_env()
init_logging()

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI()

# app = FastAPI(
#     docs_url=None,
#     redoc_url=None,
#     openapi_url=None
# )

app.include_router(admin_router)
app.include_router(match_router)
app.include_router(auth_router)
app.include_router(task_router)
app.include_router(admin_ui_router)

install_session_middleware(app)

def is_excluded(path: str) -> bool:
    excluded = (
        path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi.json")
        or path.startswith("/admin")
        or path.startswith("/admin-ui")
    )
    return excluded

@app.middleware("http")
async def verify_sign(request: Request, call_next):
    if is_excluded(request.url.path):
        return await call_next(request)

    # 读取 header
    timestamp = request.headers.get("Timestamp")
    sign = request.headers.get("Sign")

    if not timestamp or not sign:
        return JSONResponse(content=fail(-2, msg="missing sign"), status_code=400)

    # 防止重放攻击（允许 5 分钟）
    now = int(time.time())
    if abs(now - int(timestamp)) > 300:
        return JSONResponse(content=fail(-3, msg="timestamp expired"), status_code=401)

    # 读取 body
    body_bytes = await request.body()
    body = json.loads(body_bytes) if body_bytes else {}

    # 统一转字符串（避免格式问题）
    body = {k: str(v) for k, v in body.items()}

    # 校验 sign
    server_sign = generate_sign(body, timestamp)
    if server_sign != sign:
        return JSONResponse(content=fail(-4, msg="invalid sign"), status_code=401)

    # 继续执行
    response = await call_next(request)
    return response


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
