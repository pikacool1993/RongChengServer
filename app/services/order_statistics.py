from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Device, Order


def query_order_ip_device_statistics(db: Session, match_id: int) -> list[dict[str, Any]]:
    """Return order-record counts grouped by IP and device for one match.

    The aggregation intentionally counts order rows rather than tickets.  Orders
    without an IP cannot be attributed to an IP and are therefore omitted.
    """
    ip_expression = func.trim(Order.order_ip)
    device_expression = func.trim(func.coalesce(Order.device_name, ""))
    count_expression = func.count(Order.id)
    rows = (
        db.query(
            ip_expression.label("order_ip"),
            device_expression.label("device_name"),
            Order.user_id,
            Order.device_id,
            count_expression.label("order_count"),
        )
        .filter(
            Order.match_id == match_id,
            Order.order_ip.isnot(None),
            func.trim(Order.order_ip) != "",
        )
        .group_by(ip_expression, device_expression, Order.user_id, Order.device_id)
        .order_by(count_expression.desc(), ip_expression.asc(), device_expression.asc())
        .all()
    )

    device_names: dict[tuple[int | None, str | None], str] = {}
    for user_id, device_id, device_name in db.query(
        Device.user_id, Device.device_id, Device.device_name
    ).all():
        if device_name and (user_id, device_id) not in device_names:
            device_names[(user_id, device_id)] = device_name.strip()

    detail_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    for order_ip, device_name, user_id, device_id, order_count in rows:
        resolved_device_name = device_name or device_names.get((user_id, device_id), "")
        detail_counts[(order_ip, resolved_device_name)] += int(order_count or 0)

    return [
        {
            "order_ip": order_ip,
            "ip_prefix": ip_prefix(order_ip),
            "device_name": device_name or "",
            "order_count": order_count,
        }
        for (order_ip, device_name), order_count in sorted(
            detail_counts.items(), key=lambda entry: (-entry[1], entry[0][0], entry[0][1])
        )
    ]


def query_order_ip_statistics(db: Session, match_id: int) -> list[dict[str, Any]]:
    """Return the original IP-only aggregation for API compatibility."""
    ip_counts: defaultdict[str, int] = defaultdict(int)
    for item in query_order_ip_device_statistics(db, match_id):
        ip_counts[item["order_ip"]] += item["order_count"]

    return [
        {"order_ip": order_ip, "order_count": order_count}
        for order_ip, order_count in sorted(
            ip_counts.items(), key=lambda entry: (-entry[1], entry[0])
        )
    ]


def ip_prefix(order_ip: str) -> str:
    """Return the first three IPv4 segments, or a readable IPv6 /48 prefix."""
    try:
        address = ipaddress.ip_address(order_ip)
    except ValueError:
        parts = [part for part in order_ip.split(".") if part]
        return ".".join(parts[:3]) if len(parts) >= 3 else order_ip

    if address.version == 4:
        return ".".join(str(address).split(".")[:3])

    return ":".join(address.exploded.split(":")[:3]) + "::/48"


def query_order_ip_prefix_statistics(db: Session, match_id: int) -> list[dict[str, Any]]:
    """Return order-record counts grouped by the IP prefix for one match."""
    prefix_counts: defaultdict[str, int] = defaultdict(int)
    for item in query_order_ip_device_statistics(db, match_id):
        prefix_counts[item["ip_prefix"]] += item["order_count"]

    return [
        {"ip_prefix": prefix, "order_count": order_count}
        for prefix, order_count in sorted(
            prefix_counts.items(), key=lambda entry: (-entry[1], entry[0])
        )
    ]
