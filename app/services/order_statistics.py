from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Order


def query_order_ip_statistics(db: Session, match_id: int) -> list[dict[str, Any]]:
    """Return order-record counts grouped by IP for one match.

    The aggregation intentionally counts order rows rather than tickets.  Orders
    without an IP cannot be attributed to an IP and are therefore omitted.
    """
    ip_expression = func.trim(Order.order_ip)
    count_expression = func.count(Order.id)
    rows = (
        db.query(ip_expression.label("order_ip"), count_expression.label("order_count"))
        .filter(
            Order.match_id == match_id,
            Order.order_ip.isnot(None),
            func.trim(Order.order_ip) != "",
        )
        .group_by(ip_expression)
        .order_by(count_expression.desc(), ip_expression.asc())
        .all()
    )
    return [
        {"order_ip": order_ip, "order_count": int(order_count or 0)}
        for order_ip, order_count in rows
    ]
