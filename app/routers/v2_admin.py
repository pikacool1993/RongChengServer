from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ClientTask, Config, Device, Order, User, UserConfig
from ..schemas_v2 import (
    AdminUserConfigV2Request,
    AdminUserCreateV2Request,
    AdminUserPatchV2Request,
    MatchNoticeV2Request,
)
from ..v2_response import v2_success
from ..v2_security import require_admin
from ..services.order_statistics import query_order_ip_statistics


router = APIRouter(
    prefix="/v2/admin",
    tags=["v2-admin"],
    dependencies=[Depends(require_admin)],
)


def _user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "api_key": user.api_key,
        "lark_key": user.lark_key,
        "max_devices": user.max_devices,
        "role": user.role or 0,
        "created_at": user.created_at.timestamp() if user.created_at else None,
        "updated_at": user.updated_at.timestamp() if user.updated_at else None,
    }


def _decode_holders(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(req: AdminUserCreateV2Request, db: Session = Depends(get_db)):
    if db.query(User).filter(User.api_key == req.api_key).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="api key already exists")
    user = User(
        name=req.name,
        api_key=req.api_key,
        lark_key=req.lark_key,
        max_devices=req.max_devices,
        role=req.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return v2_success(_user_payload(user))


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return v2_success({"users": [_user_payload(user) for user in users]})


@router.get("/users/{user_id}")
def get_user(user_id: int = ApiPath(..., gt=0), db: Session = Depends(get_db)):
    return v2_success(_user_payload(_user_or_404(db, user_id)))


@router.patch("/users/{user_id}")
def update_user(
    req: AdminUserPatchV2Request,
    user_id: int = ApiPath(..., gt=0),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, user_id)
    fields = req.model_fields_set
    if "name" in fields:
        user.name = req.name
    if "lark_key" in fields:
        user.lark_key = req.lark_key
    if "max_devices" in fields and req.max_devices is not None:
        user.max_devices = req.max_devices
    if "role" in fields and req.role is not None:
        user.role = req.role
    user.updated_at = func.now()
    db.commit()
    db.refresh(user)
    return v2_success(_user_payload(user))


@router.delete("/users/{user_id}")
def delete_user(user_id: int = ApiPath(..., gt=0), db: Session = Depends(get_db)):
    user = _user_or_404(db, user_id)
    db.query(ClientTask).filter(ClientTask.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    return v2_success({})


@router.get("/users/{user_id}/config")
def get_user_config(user_id: int = ApiPath(..., gt=0), db: Session = Depends(get_db)):
    user = _user_or_404(db, user_id)
    row = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    config: dict[str, Any] = {}
    if row and row.config:
        try:
            parsed = json.loads(row.config)
            if isinstance(parsed, dict):
                config = parsed
        except json.JSONDecodeError:
            pass
    return v2_success(
        {
            "user_id": user.id,
            "api_key": user.api_key,
            "config": config,
            "updated_at": row.updated_at.timestamp() if row and row.updated_at else None,
        }
    )


@router.put("/users/{user_id}/config")
def put_user_config(
    req: AdminUserConfigV2Request,
    user_id: int = ApiPath(..., gt=0),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, user_id)
    row = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    config_text = json.dumps(req.config or {}, ensure_ascii=False, separators=(",", ":"))
    if row:
        row.config = config_text
        row.updated_at = func.now()
    else:
        row = UserConfig(user_id=user.id, config=config_text)
        db.add(row)
    db.commit()
    db.refresh(row)
    return v2_success(
        {
            "user_id": user.id,
            "api_key": user.api_key,
            "config": req.config or {},
            "updated_at": row.updated_at.timestamp() if row.updated_at else None,
        }
    )


@router.get("/users/{user_id}/devices")
def get_user_devices(user_id: int = ApiPath(..., gt=0), db: Session = Depends(get_db)):
    user = _user_or_404(db, user_id)
    devices = db.query(Device).filter(Device.user_id == user.id).order_by(Device.id.asc()).all()
    return v2_success(
        {
            "user_id": user.id,
            "device_count": len(devices),
            "devices": [
                {
                    "id": device.id,
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "first_seen": device.first_seen.timestamp() if device.first_seen else None,
                    "last_seen": device.last_seen.timestamp() if device.last_seen else None,
                }
                for device in devices
            ],
        }
    )


@router.get("/users/{user_id}/tickets-count")
def get_tickets_count(user_id: int = ApiPath(..., gt=0), db: Session = Depends(get_db)):
    user = _user_or_404(db, user_id)
    total = db.query(func.coalesce(func.sum(Order.ticket_count), 0)).filter(Order.user_id == user.id).scalar()
    return v2_success({"user_id": user.id, "tickets_count": int(total or 0)})


@router.get("/orders/ip-statistics")
@router.get("/orders/ip-count", include_in_schema=False)
@router.get("/orders/ip_statistics", include_in_schema=False)
def get_order_ip_statistics(
    match_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    items = query_order_ip_statistics(db, match_id)
    return v2_success(
        {
            "match_id": match_id,
            "total": sum(item["order_count"] for item in items),
            "ip_counts": items,
        }
    )


@router.put("/matches/{match_id}/notice")
def put_match_notice(
    req: MatchNoticeV2Request,
    match_id: int = ApiPath(..., gt=0),
    db: Session = Depends(get_db),
):
    config = db.query(Config).filter(Config.match_id == match_id).first()
    if config:
        config.content = req.content
    else:
        config = Config(match_id=match_id, content=req.content)
        db.add(config)
    db.commit()
    db.refresh(config)
    return v2_success({"match_id": config.match_id, "content": config.content or ""})


@router.get("/orders")
def list_orders(
    user_id: int | None = Query(default=None, gt=0),
    task_id: str | None = Query(default=None, min_length=1, max_length=128),
    device_id: str | None = Query(default=None, min_length=1, max_length=128),
    device_name: str | None = Query(default=None, min_length=1, max_length=128),
    order_ip: str | None = Query(default=None, min_length=1, max_length=45),
    match_id: int | None = Query(default=None, gt=0),
    parse_status: Literal["ok", "partial", "error", "unknown_key"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Order, User).outerjoin(User, User.id == Order.user_id)
    if user_id is not None:
        query = query.filter(Order.user_id == user_id)
    if task_id:
        query = query.filter(Order.task_id == task_id)
    if device_id:
        query = query.filter(Order.device_id == device_id)
    if device_name:
        query = query.filter(Order.device_name.like(f"%{device_name}%"))
    if order_ip:
        query = query.filter(Order.order_ip == order_ip)
    if match_id is not None:
        query = query.filter(Order.match_id == match_id)
    if parse_status:
        query = query.filter(Order.parse_status == parse_status)

    total = query.count()
    items = (
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return v2_success(
        {
            "page": page,
            "page_size": page_size,
            "total": total,
            "orders": [
                {
                    "id": order.id,
                    "user_id": order.user_id,
                    "api_key": user.api_key if user else None,
                    "task_id": order.task_id,
                    "raw_api_key": order.raw_api_key,
                    "device_id": order.device_id,
                    "device_name": order.device_name,
                    "order_ip": order.order_ip,
                    "match_id": order.match_id,
                    "ticket_count": order.ticket_count or 0,
                    "ticket_holders": _decode_holders(order.ticket_holders_json),
                    "first_delay": order.first_delay or 0,
                    "task_type": order.type or 0,
                    "parse_status": order.parse_status,
                    "parse_error": order.parse_error,
                    "customer_notified": bool(order.customer_notified),
                    "raw_payload": order.raw_payload,
                    "created_at": order.created_at.timestamp() if order.created_at else None,
                }
                for order, user in items
            ],
        }
    )
