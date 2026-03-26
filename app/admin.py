from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Device, Event

router = APIRouter(prefix="/admin", tags=["admin"])

# =========================
# 创建用户（密钥）
# =========================
@router.post("/user/create")
def create_user(api_key: str, max_devices: int  = 1, db: Session = Depends(get_db)):
    existing  = db.query(User).filter(User.api_key == api_key).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    u = User(api_key=api_key, max_devices=max_devices)
    db.add(u)
    db.commit()
    db.refresh(u)

    return {
        "status": "created",
        "user": {
            "id": u.id,
            "api_key": u.api_key,
            "max_devices": u.max_devices,
            "created_at": u.created_at
        }
    }

# =========================
# 查看所有用户（密钥）
# =========================
@router.get("/user/list")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "api_key": u.api_key,
            "max_devices": u.max_devices,
            "created_at": u.created_at,
        }
        for u in users
    ]

# =========================
# 删除用户（密钥）
# =========================
@router.delete("/user/{api_key}")
def delete_user(api_key: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(u)
    db.commit()
    return {"status": "deleted", "api_key": api_key}

# =========================
# 查看某个用户的设备
# =========================
@router.get("/user/{api_key}/devices")
def get_user_devices(api_key: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    devices = db.query(Device).filter(Device.user_id == u.id).all()
    return {
        "user": api_key,
        "device_count": len(devices),
        "devices": [
            {
                "id": d.id,
                "device_id": d.device_id,
                "first_seen": d.first_seen,
                "last_seen": d.last_seen,
            }
            for d in devices
        ],
    }

# =========================
# 查看某个用户的事件
# =========================
@router.get("/user/{api_key}/events")
def get_user_events(api_key: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    events = db.query(Event).filter(Event.user_id == u.id).all()
    return {
        "user": api_key,
        "event_count": len(events),
        "events": [
            {
                "id": e.id,
                "device_id": e.device_id,
                "event_type": e.event_type,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }

# =========================
# 全局购买统计
# =========================
@router.get("/stats/tickets_count")
def get_tickets_count(db: Session = Depends(get_db)):
    count = db.query(Event).filter(Event.event_type == "ticket_buy").count()
    return {"tickets_count": count}
