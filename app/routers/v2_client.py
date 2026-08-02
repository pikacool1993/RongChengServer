from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Config, Device, Order, User, UserConfig, now_cn
from ..response import success
from ..schemas_v2 import (
    AuthV2Request,
    EncryptedEnvelopeV2,
    MatchConfigV2Request,
    MatchDetailV2Request,
    OrderUploadV2Request,
    TaskCheckV2Request,
)
from ..services.match_api import request_match_detail
from ..v2_encrypted import V2ClientError, decode_v2_payload


router = APIRouter(prefix="/v2", tags=["v2-client"])
_MATCH_FILE = Path(__file__).resolve().parent.parent / "resources" / "match.json"


def _user_or_404(db: Session, api_key: str) -> User:
    user = db.query(User).filter(User.api_key == api_key).first()
    if not user:
        raise V2ClientError(status.HTTP_401_UNAUTHORIZED, -1001, "user not found")
    return user


def _load_config(raw_config: str | None) -> dict | str:
    if not raw_config:
        return {}
    try:
        value = json.loads(raw_config)
    except json.JSONDecodeError:
        return raw_config
    return value if isinstance(value, dict) else {}


def _touch_device(
    db: Session,
    user: User,
    device_id: str,
    device_name: str | None = None,
) -> Device | None:
    device = db.query(Device).filter_by(user_id=user.id, device_id=device_id).first()
    if device:
        device.last_seen = now_cn()
        if device_name:
            device.device_name = device_name
    return device


def _match_info() -> dict:
    if not _MATCH_FILE.exists():
        raise V2ClientError(status.HTTP_404_NOT_FOUND, -11, "match file not found")
    try:
        with _MATCH_FILE.open("r", encoding="utf-8") as handle:
            item = json.load(handle)
    except (OSError, json.JSONDecodeError):
        raise V2ClientError(status.HTTP_503_SERVICE_UNAVAILABLE, -13, "match configuration unavailable")
    if not isinstance(item, dict) or not isinstance(item.get("id"), int):
        raise V2ClientError(status.HTTP_503_SERVICE_UNAVAILABLE, -13, "match configuration unavailable")
    return item


@router.post("/auth")
def auth_v2(envelope: EncryptedEnvelopeV2, db: Session = Depends(get_db)):
    req, _ = decode_v2_payload(envelope, AuthV2Request)
    user = _user_or_404(db, req.api_key)
    device = db.query(Device).filter_by(user_id=user.id, device_id=req.device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=user.id).count()
        if device_count >= (user.max_devices or 1):
            raise V2ClientError(status.HTTP_409_CONFLICT, -1002, "device limit reached")
        device = Device(user_id=user.id, device_id=req.device_id, device_name=req.device_name)
        db.add(device)
    else:
        device.last_seen = now_cn()
        if req.device_name:
            device.device_name = req.device_name

    db.commit()
    db.refresh(device)
    user_config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    return success(
        {
            "auth_mode": "api_key",
            "role": user.role or 0,
            "config": _load_config(user_config.config if user_config else None),
            "device_id": device.device_id,
            "device_name": device.device_name,
            "t": int(time.time()),
        }
    )


@router.post("/matches/current/config")
@router.post("/matches/config", include_in_schema=False)
def current_match_config(
    envelope: EncryptedEnvelopeV2,
    db: Session = Depends(get_db),
):
    req, _ = decode_v2_payload(envelope, MatchConfigV2Request)
    _user_or_404(db, req.api_key)
    item = _match_info()
    match_id = item["id"]
    config = db.query(Config).filter_by(match_id=match_id).first()
    return success(
        {
            "info": {
                "id": match_id,
                "team1": item.get("team1_name"),
                "team2": item.get("team2_name"),
                "start": item.get("time_s"),
                "sale_start": item.get("line_s_time"),
            },
            "notice": config.content if config else "",
        }
    )


@router.post("/matches/detail")
async def match_detail_v2(
    envelope: EncryptedEnvelopeV2,
    db: Session = Depends(get_db),
):
    req, _ = decode_v2_payload(envelope, MatchDetailV2Request)
    _user_or_404(db, req.api_key)
    try:
        detail = await request_match_detail(str(req.match_id))
    except Exception:
        raise V2ClientError(status.HTTP_502_BAD_GATEWAY, -2001, "match provider unavailable")
    return success({"match_id": req.match_id, "detail": detail, "t": int(time.time())})


@router.post("/tasks/check")
def task_check_v2(
    envelope: EncryptedEnvelopeV2,
    db: Session = Depends(get_db),
):
    req, _ = decode_v2_payload(envelope, TaskCheckV2Request)
    user = _user_or_404(db, req.api_key)
    device = _touch_device(db, user, req.device_id, req.device_name)
    if not device:
        raise V2ClientError(status.HTTP_404_NOT_FOUND, -1003, "device not bound")
    db.commit()
    return success(
        {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "t": int(time.time()),
        }
    )


def _join_holder_field(holders: list[dict], key: str) -> str | None:
    values = [str(item[key]).strip() if item.get(key) is not None else "" for item in holders]
    return "&".join(values)[:128] if any(values) else None


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def upload_order_v2(
    envelope: EncryptedEnvelopeV2,
    db: Session = Depends(get_db),
):
    req, raw_payload = decode_v2_payload(envelope, OrderUploadV2Request)
    user = _user_or_404(db, req.api_key)
    device = _touch_device(db, user, req.device_id, req.device_name)
    holders = [holder.model_dump(mode="json") for holder in req.ticket_holders]
    device_name = device.device_name if device else req.device_name
    order = Order(
        user_id=user.id,
        raw_api_key=req.api_key,
        task_id=req.task_id,
        device_id=req.device_id,
        device_name=device_name,
        order_ip=req.order_ip,
        match_id=req.match_id,
        ticket_count=req.ticket_count,
        order_names=_join_holder_field(holders, "name"),
        order_cards=_join_holder_field(holders, "card"),
        order_phones=_join_holder_field(holders, "phone"),
        order_region=_join_holder_field(holders, "region"),
        order_price=_join_holder_field(holders, "price"),
        first_delay=req.first_delay,
        type=req.task_type,
        ticket_holders_json=json.dumps(holders, ensure_ascii=False, separators=(",", ":")),
        raw_payload=raw_payload,
        parse_status="ok",
    )
    db.add(order)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise V2ClientError(500, -5001, "order save failed")
    db.refresh(order)
    return success(
        {
            "order_id": order.id,
            "task_id": order.task_id,
            "parse_status": order.parse_status,
            "t": int(time.time()),
        }
    )
