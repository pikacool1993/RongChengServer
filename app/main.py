import time
import json
import os

import httpx
import smtplib
from fastapi import FastAPI, Request, Depends, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
from email.header import Header
from email.utils import formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .env import load_env
from .schemas import MatchQueryRequest, AuthRequest, TaskCheckRequest, TaskOrderRequest
from .database import SessionLocal, engine
from .models import Base, Config, User, Device, Order
from .admin import router as admin_router
from .response import success, fail
from .sign import generate_sign

load_env()

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
        base_dir = Path(__file__).resolve().parent
        file_path = base_dir / "resources" / "match.json"

        if not file_path.exists():
            return fail(-11, msg="match file not found")

        with open(file_path, "r", encoding="utf-8") as f:
            item = json.load(f)

        info = {
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
                "info": info,
                "notice": ""
            })

        return success({
            "info": info,
            "notice": c.content
        })
    except json.JSONDecodeError:
        return fail(-12, msg="invalid json format")
    except Exception as e:
        return fail(-13, msg=str(e))

@app.post("/match/detail")
async def match_detail(req: MatchQueryRequest, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "status": 2,
            "desc": "user not found",
            "t": now
        })

    try:
        detail = await request_match_detail(req.match_id)
        return success({
            "status": 1,
            "detail": detail,
            "desc": "ok",
            "t": now
        })

    except Exception as e:
        return success({
            "status": -1,
            "desc": str(e),
            "t": now
        })

@app.post("/auth")
def auth(req: AuthRequest, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "status": 2,
            "desc": "user not found",
            "t": now
        })

    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=user.id).count()
        if device_count >= user.max_devices:
            return success({
                "status": 3,
                "desc": "device limit reached",
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
        "status": 1,
        "api_key": user.api_key,
        "device_id": device.device_id,
        "desc": "ok",
        "t": now
    })

@app.post("/task/check")
def task_check(req: TaskCheckRequest, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "status": 2,
            "desc": "user not found",
            "t": now
        })

    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()
    if not device:
        return success({
            "status": 3,
            "desc": "refuse",
            "t": now
        })
    else:
        return success({
            "status": 1,
            "api_key": user.api_key,
            "device_id": device.device_id,
            "desc": "ok",
            "t": now
        })

@app.post("/task/order")
def task_order(req: TaskOrderRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({
            "status": 2,
            "desc": "user not found",
            "t": now
        })

    db.add(Order(
        user_id=user.id,
        device_id=req.device_id,
        match_id=req.match_id,
        ticket_count=req.ticket_count,
        order_names=req.order_names,
        order_region=req.order_region,
        order_price=req.order_price
    ))
    db.commit()

    if req.email and req.email.strip():
        background_tasks.add_task(send_email, req.email, req.email_content)

    return success({
        "status": 1,
        "desc": "ok",
        "t": now
    })

def send_email(target_mail: str, mail_content: str):
    try:
        sender_name = os.getenv("SMTP_SENDER_NAME", "凤凰山票务")
        sender_email = os.getenv("SMTP_USER")
        sender_password = os.getenv("SMTP_PASSWORD")

        smtp_server = os.getenv("SMTP_HOST", "smtp.qq.com")
        smtp_port = int(os.getenv("SMTP_PORT", "465"))  # SSL

        if not sender_email or not sender_password:
            print("SMTP 未配置（缺少 SMTP_USER/SMTP_PASSWORD），已跳过发信。")
            return

        # ====== 构建邮件 ======
        msg = MIMEMultipart()
        msg["From"] = formataddr((Header(sender_name, "utf-8").encode(), sender_email))
        msg["To"] = target_mail
        msg["Subject"] = Header("购票成功", "utf-8")

        body = MIMEText(mail_content, "html", "utf-8")
        msg.attach(body)

        # ====== 发送 ======
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [target_mail], msg.as_string())
        print("邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")


