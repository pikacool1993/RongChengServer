from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Config, User
from ..response import fail, success
from ..schemas import MatchQueryRequest
from ..services.match_api import request_match_detail

router = APIRouter(tags=["match"])


@router.get("/match/config")
def match_config(db: Session = Depends(get_db)):
    try:
        base_dir = Path(__file__).resolve().parent.parent
        file_path = base_dir / "resources" / "match.json"

        if not file_path.exists():
            return fail(-11, msg="match file not found")

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
        if not c:
            return success({"info": info, "notice": ""})

        return success({"info": info, "notice": c.content})
    except json.JSONDecodeError:
        return fail(-12, msg="invalid json format")
    except Exception as e:
        return fail(-13, msg=str(e))


@router.post("/match/detail")
async def match_detail(req: MatchQueryRequest, db: Session = Depends(get_db)):
    now = int(time.time())
    user = db.query(User).filter_by(api_key=req.api_key).first()
    if not user:
        return success({"status": 2, "desc": "user not found", "t": now})

    try:
        detail = await request_match_detail(req.match_id)
        return success({"status": 1, "detail": detail, "desc": "ok", "t": now})
    except Exception as e:
        return success({"status": -1, "desc": str(e), "t": now})

