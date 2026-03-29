import time
import json
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from datetime import datetime

from .schemas import AuthRequest, EventRequest
from .database import SessionLocal, engine
from .models import Base, User, Device, Event
from .admin import router as admin_router
from .response import success, fail
from .sign import generate_sign

Base.metadata.create_all(bind=engine)

app = FastAPI()

# app = FastAPI(
#     docs_url=None,
#     redoc_url=None,
#     openapi_url=None
# )

app.include_router(admin_router)

def is_excluded(path: str) -> bool:
    excluded = (
        path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi.json")
        or path.startswith("/admin")
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
        return JSONResponse(content=fail(-2, msg="missing sign"), status_code=200)

    # 防止重放攻击（允许 5 分钟）
    now = int(time.time())
    if abs(now - int(timestamp)) > 300:
        return JSONResponse(content=fail(-3, msg="timestamp expired"), status_code=200)

    # 读取 body
    body_bytes = await request.body()
    body = json.loads(body_bytes) if body_bytes else {}

    # 校验 sign
    server_sign = generate_sign(body, timestamp)
    if server_sign != sign:
        return JSONResponse(content=fail(-4, msg="invalid sign"), status_code=200)

    # 继续执行
    response = await call_next(request)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=200,
        content=fail(-200, msg=str(exc))
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content=fail(-100, msg=str(exc))
    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/auth")
def auth(req: AuthRequest, db: Session = Depends(get_db)):
    api_key = req.api_key
    device_id = req.device_id
    now = int(time.time())

    u = db.query(User).filter_by(api_key=api_key).first()
    if not u:
        return success({
            "auth_status": 2,
            "t": now
        })

    device = db.query(Device).filter_by(user_id=u.id, device_id=device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=u.id).count()

        if device_count >= u.max_devices:
            return success({
                "auth_status": 3,
                "t": now
            })

        db.add(Device(
            user_id=u.id,
            device_id=device_id
        ))
    else:
        device.last_seen = datetime.now()

    db.commit()

    return success({
        "auth_status": 1,
        "device_id": device_id,
        "api_key": api_key,
        "t": now
    })

@app.post("/event")
def log_event(req: EventRequest, db: Session = Depends(get_db)):
    api_key = req.api_key
    device_id = req.device_id
    event = req.event

    u = db.query(User).filter_by(api_key=api_key).first()

    if not u:
        return success({
            "status": 2
        })

    db.add(Event(
        user_id=u.id,
        device_id=device_id,
        event_type=event
    ))
    db.commit()

    return success({
        "status": 1
    })
