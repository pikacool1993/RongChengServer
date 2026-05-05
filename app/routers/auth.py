from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Device, User, now_cn
from ..response import success
from ..schemas import AuthRequest

router = APIRouter(tags=["auth"])

@router.post("/auth")
def auth(req: AuthRequest, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({"status": 2, "desc": "user not found", "t": now})

    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=user.id).count()
        if device_count >= user.max_devices:
            return success({"status": 3, "desc": "device limit reached", "t": now})

        db.add(Device(user_id=user.id, device_id=req.device_id))
    else:
        device.last_seen = now_cn()

    db.commit()

    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()

    return success(
        {
            "status": 1,
            "api_key": user.api_key,
            "device_id": device.device_id,
            "desc": "ok",
            "t": now,
        }
    )

