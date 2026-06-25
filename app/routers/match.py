from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Config, User
from ..response import fail, success
from ..services.match_api import request_match_detail
from .encrypted import read_encrypted_request

router = APIRouter(tags=["match"])


@router.post("/match/config")
async def match_config(request: Request, db: Session = Depends(get_db)):
    _, _, error = await read_encrypted_request(request)
    if error:
        return error

    try:
        base_dir = Path(__file__).resolve().parent.parent
        file_path = base_dir / "resources" / "match.json"

        if not file_path.exists():
            return fail(-11, msg="match file not found", encrypt=True)

        with open(file_path, "r", encoding="utf-8") as f:
            item = json.load(f)

        info = {
            "id": item.get("id"),
            "team1": item.get("team1_name"),
            "team2": item.get("team2_name"),
            "start": item.get("time_s"),
            "sale_start": item.get("line_s_time"),
        }
        match_id = item.get("id")

        c = db.query(Config).filter_by(match_id=match_id).first()
        return success({"info": info, "notice": c.content if c else ""})
    except json.JSONDecodeError:
        return fail(-12, msg="invalid json format", encrypt=True)
    except Exception as e:
        return fail(-13, msg=str(e), encrypt=True)


@router.post("/match/detail")
async def match_detail(request: Request, db: Session = Depends(get_db)):
    req, _, error = await read_encrypted_request(request)
    if error:
        return error

    now = int(time.time())
    api_key = str(req.get("api_key") or "")
    match_id = str(req.get("match_id") or "")
    user = db.query(User).filter_by(api_key=api_key).first()
    if not user:
        return fail(-1001, msg="user not found", encrypt=True)

    try:
        detail = await request_match_detail(match_id)
        return success({"detail": detail, "t": now})
    except Exception as e:
        return fail(-2001, msg=str(e), encrypt=True)
