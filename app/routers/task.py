from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Device, Order, User
from ..response import success
from ..schemas import TaskCheckRequest, TaskOrderRequest

router = APIRouter(tags=["task"])

@router.post("/task/check")
def task_check(req: TaskCheckRequest, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({"status": 2, "desc": "user not found", "t": now})

    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()
    if not device:
        return success({"status": 3, "desc": "refuse", "t": now})

    return success(
        {"status": 1, "api_key": user.api_key, "device_id": device.device_id, "desc": "ok", "t": now}
    )

@router.post("/task/order")
def task_order(req: TaskOrderRequest, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({"status": 2, "desc": "user not found", "t": now})

    db.add(
        Order(
            user_id = user.id,
            device_id = req.device_id,
            match_id = req.match_id,
            ticket_count = req.ticket_count,
            order_names = req.order_names,
            order_cards = req.order_cards,
            order_phones = req.order_phones,
            order_region = req.order_region,
            order_price = req.order_price,
            first_delay = req.first_delay,
            first_start_t = req.first_start_t,
            first_end_t = req.first_end_t,
            type = req.type
        )
    )
    db.commit()
    return success({"status": 1, "desc": "ok", "t": now})

