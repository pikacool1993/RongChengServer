from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Order

_MATCH_FILE = Path(__file__).resolve().parent.parent / "resources" / "match.json"


def load_match_info() -> dict | None:
    if not _MATCH_FILE.exists():
        return None
    with open(_MATCH_FILE, "r", encoding="utf-8") as f:
        item = json.load(f)
    if not isinstance(item.get("id"), int):
        return None
    return item


def _order_names_contains(order_names: str | None, name: str) -> bool:
    if not order_names:
        return False
    names = [n.strip() for n in order_names.split("&") if n.strip()]
    return name in names


def query_orders_by_name(db: Session, name: str) -> list[dict[str, str | None]]:
    name = name.strip()
    if not name:
        return []

    match_info = load_match_info()
    if not match_info:
        return []

    orders = db.query(Order).filter(Order.match_id == match_info["id"]).all()
    results: list[dict[str, str | None]] = []
    for o in orders:
        if not _order_names_contains(o.order_names, name):
            continue
        results.append(
            {
                "order_names": o.order_names,
                "order_region": o.order_region,
            }
        )
    return results
