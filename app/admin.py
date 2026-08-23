import os

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .schemas import (
    AdminCreateUserRequest,
    AdminCreateConfigRequest,
    AdminUpdateUserRequest,
    AdminUpsertUserConfigRequest,
)
from .database import get_db
from .models import ClientTask, Config, User, UserConfig, Device, Order
from .response import success, fail
from .env import load_env
from .services.order_statistics import (
    query_order_ip_prefix_statistics,
    query_order_ip_statistics,
    query_order_ip_device_statistics,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# =========================
# 全局常量
# =========================
load_env()
ADMIN_PASSWORD: str | None = os.getenv("ADMIN_PASSWORD")

# =========================
# 公共工具函数（消除重复代码）
# =========================
def verify_password(password: str):
    """验证管理员密码"""
    if not ADMIN_PASSWORD:
        return fail(msg="Admin password not configured")
    if password != ADMIN_PASSWORD:
        return fail(msg="Wrong password")
    return None


def normalize_role(role: int | None) -> int:
    return 1 if role == 1 else 0

# =========================
# 创建更新配置
# =========================
@router.post("/match/config")
def create_config(req: AdminCreateConfigRequest, db: Session = Depends(get_db)):
    match_id = req.match_id
    content = req.content
    password = req.password

    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    existing = db.query(Config).filter(Config.match_id == match_id).first()
    if existing:
        existing.content = content
        db.commit()
        db.refresh(existing)

        return success({
            "status": 1
        }, encrypt=False)

    c = Config(match_id=match_id, content=content)
    db.add(c)
    db.commit()

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
    lark_key = req.lark_key
    max_devices = req.max_devices
    role = normalize_role(req.role)
    password = req.password

    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    existing = db.query(User).filter(User.api_key == api_key).first()
    if existing:
        existing.name = name
        existing.lark_key = lark_key
        existing.max_devices = max_devices
        existing.role = role
        db.commit()
        db.refresh(existing)

        return success({
            "id": existing.id,
            "name": existing.name,
            "api_key": existing.api_key,
            "lark_key": existing.lark_key,
            "max_devices": existing.max_devices,
            "role": existing.role or 0,
            "created_at": existing.created_at.timestamp()
        }, encrypt=False)

    u = User(name=name, api_key=api_key, lark_key=lark_key, max_devices=max_devices, role=role)
    db.add(u)
    db.commit()
    db.refresh(u)

    return success({
        "id": u.id,
        "name": u.name,
        "api_key": u.api_key,
        "lark_key": u.lark_key,
        "max_devices": u.max_devices,
        "role": u.role or 0,
        "created_at": u.created_at.timestamp()
    }, encrypt=False)

# =========================
# 删除用户（密钥）
# =========================
@router.delete("/user/delete")
def delete_user(api_key: str, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return fail(msg="User not found")

    db.query(ClientTask).filter(ClientTask.user_id == u.id).delete(synchronize_session=False)
    db.delete(u)
    db.commit()
    return success({}, encrypt=False)

# =========================
# 更新用户（按 api_key）
# =========================
@router.put("/user/update")
def update_user(req: AdminUpdateUserRequest, db: Session = Depends(get_db)):
    pwd_error = verify_password(req.password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == req.api_key).first()
    if not u:
        return fail(msg="User not found")

    if req.name is not None:
        u.name = req.name
    if req.lark_key is not None:
        u.lark_key = req.lark_key
    if req.max_devices is not None:
        u.max_devices = req.max_devices
    if req.role is not None:
        u.role = normalize_role(req.role)
    u.updated_at = func.now()
    db.commit()
    db.refresh(u)

    return success(
        {
            "id": u.id,
            "name": u.name,
            "api_key": u.api_key,
            "lark_key": u.lark_key,
            "max_devices": u.max_devices,
            "role": u.role or 0,
            "created_at": u.created_at.timestamp(),
            "updated_at": u.updated_at.timestamp() if u.updated_at else None,
        },
        encrypt=False,
    )

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
                "name": u.name,
                "api_key": u.api_key,
                "lark_key": u.lark_key,
                "max_devices": u.max_devices,
                "role": u.role or 0,
                "created_at": u.created_at.timestamp(),
                "updated_at": u.updated_at.timestamp() if u.updated_at else None,
            }
            for u in users
        ]
    }, encrypt=False)


# =========================
# api_key 对应配置
# =========================
@router.post("/user/config")
def upsert_user_config(req: AdminUpsertUserConfigRequest, db: Session = Depends(get_db)):
    pwd_error = verify_password(req.password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == req.api_key).first()
    if not u:
        return fail(msg="User not found")

    config_text = (req.config or "").strip()
    if config_text:
        try:
            json.loads(config_text)
        except json.JSONDecodeError:
            return fail(msg="Config must be valid JSON")

    row = db.query(UserConfig).filter(UserConfig.user_id == u.id).first()
    if row:
        row.config = config_text
        row.updated_at = func.now()
    else:
        row = UserConfig(user_id=u.id, config=config_text)
        db.add(row)

    db.commit()
    db.refresh(row)
    return success(
        {
            "api_key": u.api_key,
            "config": json.loads(row.config) if row.config else {},
            "updated_at": row.updated_at.timestamp() if row.updated_at else None,
        },
        encrypt=False,
    )


@router.get("/user/config")
def get_user_config(api_key: str, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return fail(msg="User not found")

    row = db.query(UserConfig).filter(UserConfig.user_id == u.id).first()
    config_text = row.config if row else ""
    return success(
        {
            "api_key": u.api_key,
            "config": json.loads(config_text) if config_text else {},
            "updated_at": row.updated_at.timestamp() if row and row.updated_at else None,
        },
        encrypt=False,
    )

# =========================
# 查看某个用户的设备
# =========================
@router.get("/user/devices")
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
                "device_name": d.device_name,
                "first_seen": d.first_seen.timestamp(),
                "last_seen": d.last_seen.timestamp(),
            }
            for d in devices
        ],
    }, encrypt=False)

# =========================
# api_key任务出票统计
# =========================
@router.get("/task/tickets_count")
def get_tickets_count(api_key: str, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return fail(msg="User not found")

    total_tickets = db.query(func.sum(Order.ticket_count)).filter(Order.user_id == u.id).scalar() or 0

    return success({
        "tickets_count": total_tickets
    }, encrypt=False)


# =========================
# 按比赛统计下单 IP 的订单数
# =========================
@router.get("/orders/ip_count")
@router.get("/task/ip_count", include_in_schema=False)
@router.get("/orders/ip_statistics", include_in_schema=False)
@router.get("/orders/ip-statistics", include_in_schema=False)
def get_order_ip_statistics(match_id: int, password: str, db: Session = Depends(get_db)):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error
    if match_id <= 0:
        return fail(msg="match_id must be a positive integer")

    items = query_order_ip_statistics(db, match_id)
    device_items = query_order_ip_device_statistics(db, match_id)
    prefix_items = query_order_ip_prefix_statistics(db, match_id)
    return success(
        {
            "match_id": match_id,
            "total": sum(item["order_count"] for item in items),
            "ip_counts": items,
            "ip_device_counts": device_items,
            "ip_prefix_counts": prefix_items,
        },
        encrypt=False,
    )


# =========================
# 订单列表（支持筛选 + 分页）
# =========================
@router.get("/orders/list")
def list_orders(
    password: str,
    api_key: str | None = None,
    raw_api_key: str | None = None,
    device_id: str | None = None,
    device_name: str | None = None,
    match_id: int | None = None,
    parse_status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    pwd_error = verify_password(password)
    if pwd_error:
        return pwd_error

    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 200:
        page_size = 200

    q = db.query(Order, User).outerjoin(User, User.id == Order.user_id)

    if api_key:
        q = q.filter(User.api_key == api_key)
    if raw_api_key:
        q = q.filter(Order.raw_api_key == raw_api_key)
    if device_id:
        q = q.filter(Order.device_id == device_id)
    if device_name:
        q = q.filter(Order.device_name.like(f"%{device_name}%"))
    if match_id is not None:
        q = q.filter(Order.match_id == match_id)
    if parse_status:
        q = q.filter(Order.parse_status == parse_status)

    total = q.count()
    items = (
        q.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return success(
        {
            "page": page,
            "page_size": page_size,
            "total": total,
            "orders": [
                {
                    "id": o.id,
                    "api_key": u.api_key if u else None,
                    "raw_api_key": o.raw_api_key,
                    "has_user": u is not None,
                    "user_id": o.user_id,
                    "device_id": o.device_id,
                    "device_name": o.device_name,
                    "order_ip": o.order_ip,
                    "match_id": o.match_id,
                    "ticket_count": o.ticket_count,
                    "order_names": o.order_names,
                    "order_cards": o.order_cards,
                    "order_phones": o.order_phones,
                    "order_region": o.order_region,
                    "order_price": o.order_price,
                    "type": o.type,
                    "raw_payload": o.raw_payload,
                    "parse_status": o.parse_status,
                    "parse_error": o.parse_error,
                    "customer_notified": bool(o.customer_notified),
                    "created_at": o.created_at.timestamp() if o.created_at else None,
                }
                for (o, u) in items
            ],
        },
        encrypt=False,
    )
