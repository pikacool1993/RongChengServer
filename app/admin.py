from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .schemas import AdminCreateUserRequest, AdminCreateConfigRequest
from .database import get_db
from .models import Config, User, Device, Event
from .response import success, fail

router = APIRouter(prefix="/admin", tags=["admin"])

# =========================
# 全局常量
# =========================
FIXED_PASSWORD: str = "VvHw5Gi5zFvfCRpD"

# =========================
# 公共工具函数（消除重复代码）
# =========================
def verify_password(password: str):
    """验证管理员密码"""
    if password != FIXED_PASSWORD:
        return fail(msg="Wrong password")
    return None

# =========================
# 创建更新配置
# =========================
@router.post("/create/config")
def create_config(req: AdminCreateConfigRequest, db: Session = Depends(get_db)):
    match_id = req.match_id
    content = req.content
    password = req.password

    pwd_error = verify_password(req.password)
    if pwd_error:
        return pwd_error

    existing = db.query(Config).filter(Config.match_id == match_id).first()
    if existing:
        return success({
            "status": 1
        }, encrypt=False)

    c = Config(match_id=match_id, content=content)
    db.add(c)
    db.commit()
    db.refresh(c)

    return success({
                "status": 1
            }, encrypt=False)

# =========================
# 创建用户（密钥）
# =========================
@router.post("/user/create")
def create_user(req: AdminCreateUserRequest, db: Session = Depends(get_db)):
    name = req.name
    api_key = req.api_key
    max_devices = req.max_devices
    password = req.password

    pwd_error = verify_password(req.password)
    if pwd_error:
        return pwd_error

    existing  = db.query(User).filter(User.api_key == api_key).first()
    if existing:
        return fail(msg="User already exists")

    u = User(name=name, api_key=api_key, max_devices=max_devices)
    db.add(u)
    db.commit()
    db.refresh(u)

    return success({
        "id": u.id,
        "name": u.name,
        "api_key": u.api_key,
        "max_devices": u.max_devices,
        "created_at": u.created_at.timestamp()
    }, encrypt=False)

# =========================
# 查看所有用户（密钥）
# =========================
@router.get("/user/list")
def list_users(password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    users = db.query(User).all()
    return success({
        "users": [
            {
                "id": u.id,
                "api_key": u.api_key,
                "max_devices": u.max_devices,
                "created_at": u.created_at.timestamp(),
            }
            for u in users
        ]
    }, encrypt=False)

# =========================
# 删除用户（密钥）
# =========================
@router.delete("/user/{api_key}")
def delete_user(api_key: str, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return fail(msg="User not found")

    db.delete(u)
    db.commit()
    return success({}, encrypt=False)

# =========================
# 查看某个用户的设备
# =========================
@router.get("/user/{api_key}/devices")
def get_user_devices(api_key: str, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return fail(msg="User not found")

    devices = db.query(Device).filter(Device.user_id == u.id).all()
    return success({
        "user": api_key,
        "device_count": len(devices),
        "devices": [
            {
                "id": d.id,
                "device_id": d.device_id,
                "first_seen": d.first_seen.timestamp(),
                "last_seen": d.last_seen.timestamp(),
            }
            for d in devices
        ],
    }, encrypt=False)

# =========================
# 查看某个用户的事件
# =========================
@router.get("/user/{api_key}/events")
def get_user_events(api_key: str, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return fail(msg="User not found")

    events = db.query(Event).filter(Event.user_id == u.id).all()
    return success({
        "user": api_key,
        "event_count": len(events),
        "events": [
            {
                "id": e.id,
                "device_id": e.device_id,
                "event_type": e.event_type,
                "created_at": e.created_at.timestamp(),
            }
            for e in events
        ],
    }, encrypt=False)

# =========================
# 全局购买统计
# =========================
@router.get("/stats/tickets_count")
def get_tickets_count(password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    count = db.query(Event).filter(Event.event_type == "ticket_buy").count()
    return success({
        "tickets_count": count
    }, encrypt=False)

# =========================
# api_key购买统计
# =========================
@router.get("/stats/{api_key}/tickets_count")
def get_tickets_count(api_key: str, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return fail(msg="User not found")

    count = db.query(Event).filter(Event.user_id == u.id).count()
    return success({
        "tickets_count": count
    }, encrypt=False)
