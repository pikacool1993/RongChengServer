from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import Order, User

_MATCH_FILE = Path(__file__).resolve().parent.parent / "resources" / "match.json"


@dataclass(frozen=True)
class ApiKeyOrderPage:
    key_valid: bool
    orders: list[dict[str, Any]]
    total: int
    tickets_sum: int
    page: int
    page_size: int
    total_pages: int


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

    name = name.strip()
    name_filters = [
        Order.order_names == name,
        Order.order_names.like(f"{name}&%"),
        Order.order_names.like(f"%&{name}&%"),
        Order.order_names.like(f"%&{name}"),
    ]
    orders = (
        db.query(Order)
        .filter(
            Order.match_id == match_info["id"],
            Order.order_names.isnot(None),
            Order.order_region.isnot(None),
            or_(*name_filters),
        )
        .all()
    )
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


def query_orders_by_api_key(
    db: Session,
    api_key: str,
    *,
    match_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ApiKeyOrderPage:
    api_key = api_key.strip()
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    if not api_key:
        return ApiKeyOrderPage(False, [], 0, 0, page, page_size, 1)

    user = db.query(User).filter(User.api_key == api_key).first()
    if not user:
        return ApiKeyOrderPage(False, [], 0, 0, page, page_size, 1)

    query = (
        db.query(Order)
        .filter(or_(Order.user_id == user.id, Order.raw_api_key == api_key))
    )
    if match_id is not None:
        query = query.filter(Order.match_id == match_id)

    total = query.count()
    tickets_sum = int(query.with_entities(func.coalesce(func.sum(Order.ticket_count), 0)).scalar() or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    orders = (
        query
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        {
            "match_id": order.match_id,
            "device_name": order.device_name,
            "order_names": order.order_names,
            "ticket_count": order.ticket_count or 0,
            "order_region": order.order_region,
            "order_price": order.order_price,
            "created_at": order.created_at,
        }
        for order in orders
    ]
    return ApiKeyOrderPage(True, items, total, tickets_sum, page, page_size, total_pages)
