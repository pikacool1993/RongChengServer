from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Device, Order, User, now_cn
from ..response import fail, success
from .encrypted import read_encrypted_request

router = APIRouter(tags=["task"])


def _clean_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:128] if text else None


def _clean_int(req: dict, key: str, default: int = 0) -> tuple[int, str | None]:
    if key not in req or req.get(key) in (None, ""):
        return default, f"missing field: {key}"
    try:
        return int(req.get(key)), None
    except (TypeError, ValueError):
        return default, f"invalid int field: {key}"


def _update_device_name_if_known(db: Session, user_id: int, device_id: str | None, device_name: str | None) -> None:
    if not device_id:
        return
    device = db.query(Device).filter_by(user_id=user_id, device_id=device_id).first()
    if device:
        device.last_seen = now_cn()
        if device_name:
            device.device_name = device_name


@router.post("/task/check")
async def task_check(request: Request, db: Session = Depends(get_db)):
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
        return fail(-1003, msg="device not bound", encrypt=True)

    device.last_seen = now_cn()
    if device_name:
        device.device_name = device_name
    db.commit()

    return success(
        {
            "api_key": user.api_key,
            "device_id": device.device_id,
            "device_name": device.device_name,
            "t": now,
        }
    )


@router.post("/task/order")
async def task_order(request: Request, db: Session = Depends(get_db)):
    req, raw_payload, error = await read_encrypted_request(request)
    if error:
        return error

    now = int(time.time())
    api_key = _clean_str(req.get("api_key"))
    device_id = _clean_str(req.get("device_id"))
    device_name = _clean_str(req.get("device_name"))
    errors: list[str] = []

    user = db.query(User).filter_by(api_key=api_key).first() if api_key else None
    if not user:
        errors.append("unknown api_key" if api_key else "missing field: api_key")

    match_id, err = _clean_int(req, "match_id", default=0)
    if err:
        errors.append(err)
        match_id_value = None
    else:
        match_id_value = match_id

    ticket_count, err = _clean_int(req, "ticket_count", default=0)
    if err:
        errors.append(err)

    first_delay, err = _clean_int(req, "first_delay", default=0)
    if err:
        errors.append(err)

    task_type, err = _clean_int(req, "type", default=0)
    if err:
        errors.append(err)

    for key in (
        "device_id",
        "order_names",
        "order_cards",
        "order_phones",
        "order_region",
        "order_price",
        "first_start_t",
        "first_end_t",
    ):
        if key not in req or req.get(key) in (None, ""):
            errors.append(f"missing field: {key}")

    if user:
        _update_device_name_if_known(db, user.id, device_id, device_name)

    parse_status = "ok"
    if not user:
        parse_status = "unknown_key"
    elif errors:
        parse_status = "partial"

    order = Order(
        user_id=user.id if user else None,
        raw_api_key=api_key,
        device_id=device_id,
        device_name=device_name,
        match_id=match_id_value,
        ticket_count=ticket_count,
        order_names=_clean_str(req.get("order_names")),
        order_cards=_clean_str(req.get("order_cards")),
        order_phones=_clean_str(req.get("order_phones")),
        order_region=_clean_str(req.get("order_region")),
        order_price=_clean_str(req.get("order_price")),
        first_delay=first_delay,
        first_start_t=_clean_str(req.get("first_start_t")),
        first_end_t=_clean_str(req.get("first_end_t")),
        type=task_type,
        raw_payload=raw_payload,
        parse_status=parse_status,
        parse_error="; ".join(errors) if errors else None,
    )
    db.add(order)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return fail(-5001, msg="order save failed", encrypt=True)
    db.refresh(order)

    data = {
        "order_id": order.id,
        "parse_status": parse_status,
        "t": now,
    }
    if order.parse_error:
        data["parse_error"] = order.parse_error
    return success(data)
