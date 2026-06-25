from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Device, User, now_cn
from ..response import fail, success
from .encrypted import read_encrypted_request

router = APIRouter(tags=["auth"])


@router.post("/auth")
async def auth(request: Request, db: Session = Depends(get_db)):
    req, _, error = await read_encrypted_request(request)
    if error:
        return error

    now = int(time.time())
    api_key = str(req.get("api_key") or "")
    device_id = str(req.get("device_id") or "")
    device_name = str(req.get("device_name") or "").strip() or None

    user = db.query(User).filter_by(api_key=api_key).first()
    if not user:
        return fail(-1001, msg="user not found", encrypt=True)

    device = db.query(Device).filter_by(user_id=user.id, device_id=device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=user.id).count()
        if device_count >= user.max_devices:
            return fail(-1002, msg="device limit reached", encrypt=True)

        device = Device(user_id=user.id, device_id=device_id, device_name=device_name)
        db.add(device)
    else:
        device.last_seen = now_cn()
        if device_name:
            device.device_name = device_name

    db.commit()
    db.refresh(device)

    return success(
        {
            "api_key": user.api_key,
            "lark_key": user.lark_key,
            "device_id": device.device_id,
            "device_name": device.device_name,
            "t": now,
        }
    )
