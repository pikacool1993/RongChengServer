import time
import json
import httpx
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path

from .schemas import MatchQueryRequest, AuthRequest, TaskCreateRequest, TaskUpdateRequest
from .database import SessionLocal, engine
from .models import Base, Config, User, Device, TaskEvent
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

    # 统一转字符串（避免格式问题）
    body = {k: str(v) for k, v in body.items()}

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

async def request_match_detail(match_id: str):
    url = "https://fccdn1.k4n.cc/fc/wx_api/v1/MiniApp/getMatchInfo?lid2=255143"
    headers = {
        "Authorization" : "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOjI1NTE0Mywib2lkIjoiY2IwZDRiYjA2ODNhZmVmMWFiOGNlMzE4ZjdkNTZlMzMiLCJsaWQiOjAsInNpZGUiOiJ3eF9hcGkiLCJhdWQiOiIiLCJleHAiOjE3NzU2MzkyMTAsImlhdCI6MTc3NTU2NzIxMCwiaXNzIjoiIiwianRpIjoiYTE4Njc3NTRhMmUyOThhZGVhOWNkZjViM2NjNzBkMTciLCJuYmYiOjE3NzU1NjcyMTAsInN1YiI6IiJ9.vve1yTdwrdsvBjU3HEMxeBM_KJ5N7eQLGxppEEKnoes",
        "User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254181d) XWEB/19201",
        "xweb_xhr" : "1",
        "Content-Type" : "application/json;charset:utf-8;",
        "Accept" : "*/*",
        "Sec-Fetch-Site" : "cross-site",
        "Sec-Fetch-Mode" : "cors",
        "Sec-Fetch-Dest" : "empty",
        "Referer" : "https://servicewechat.com/wxffa42ecd6c0e693d/78/page-frame.html",
        "Accept-Encoding" : "gzip, deflate, br",
        "Accept-Language" : "zh-CN,zh;q=0.9"
    }
    body = {
        "id": match_id
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

@app.get("/match/config")
def match(db: Session = Depends(get_db)):
    try:
        BASE_DIR = Path(__file__).resolve().parent
        file_path = BASE_DIR / "resources" / "match.json"

        if not file_path.exists():
            return fail(-11, msg="match file not found")

        with open(file_path, "r", encoding="utf-8") as f:
            item = json.load(f)

        result = {
            "id": item.get("id"),
            "team1": item.get("team1_name"),
            "team2": item.get("team2_name"),
            "start": item.get("time_s"),
            "sale_start": item.get("line_s_time")
        }

        match_id = item.get("id")

        c = db.query(Config).filter_by(match_id=match_id).first()
        if not c:
            return success({
                "data": result
            })

        return success({
            "data": result,
            "notice": c.content
        })
    except json.JSONDecodeError:
        return fail(-12, msg="invalid json format")
    except Exception as e:
        return fail(-13, msg=str(e))

@app.post("/match/detail")
async def match_detail(req: MatchQueryRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "status": 2,
            "detail": {},
            "error": "user not found"
        })

    try:
        detail = await request_match_detail(req.match_id)
        return success({
            "status": 1,
            "detail": detail
        })

    except Exception as e:
        return success({
            "status": -1,
            "detail": {},
            "error": str(e)
        })

@app.post("/auth")
def auth(req: AuthRequest, db: Session = Depends(get_db)):
    now = int(time.time())

    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "auth_status": 2,
            "t": now
        })

    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=user.id).count()

        if device_count >= user.max_devices:
            return success({
                "auth_status": 3,
                "t": now
            })

        db.add(Device(
            user_id=user.id,
            device_id=req.device_id
        ))
    else:
        device.last_seen = datetime.now()

    db.commit()

    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()

    return success({
        "auth_status": 1,
        "device_id": device.device_id,
        "api_key": user.api_key,
        "uid": user.id,
        "t": now
    })

@app.post("/task/create")
def task_create(req: TaskCreateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "status": 2
        })

    task = TaskEvent(
        user_id=user.id,
        device_id=req.device_id,
        match_id=req.match_id
    )

    db.add(task)
    db.flush()

    task_id = task.id
    db.commit()

    return success({
        "status": 1,
        "task": {
            "id": task_id
        }
    })

@app.post("/task/update")
def task_update(req: TaskUpdateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "status": 2
        })

    task = db.query(TaskEvent).filter_by(id=req.task_id, api_key=req.api_key).first()
    if not task:
        return success({
            "status": 3
        })

    task.status = req.status
    task.ticket_count = req.ticket_count

    db.commit()
    return success({
        "status": 1
    })
