from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.order_query import query_orders_by_api_key, query_orders_by_name
from ..services.rate_limit_service import check_query_rate_limit, get_query_cooldown_seconds

router = APIRouter(tags=["order-query-ui"])
ORDER_PAGE_SIZES = (10, 20, 50, 100)

templates = Jinja2Templates(directory=str(os.path.join(os.path.dirname(__file__), "..", "templates")))

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _render(
    request: Request,
    *,
    name: str = "",
    submitted: bool = False,
    results: list[dict[str, str | None]] | None = None,
    rate_limited: bool = False,
    retry_after: int = 0,
):
    return templates.TemplateResponse(
        "query.html",
        {
            "request": request,
            "name": name,
            "submitted": submitted,
            "results": results,
            "rate_limited": rate_limited,
            "retry_after": retry_after,
            "cooldown_seconds": get_query_cooldown_seconds(),
        },
    )


def _render_orders(
    request: Request,
    *,
    api_key: str = "",
    match_id: str = "",
    page_size: int = 20,
    page: int = 1,
    total: int = 0,
    tickets_sum: int = 0,
    total_pages: int = 1,
    submitted: bool = False,
    orders: list[dict[str, Any]] | None = None,
    error: str = "",
):
    order_items = orders or []
    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "api_key": api_key,
            "match_id": match_id,
            "page_size": page_size,
            "page_size_options": ORDER_PAGE_SIZES,
            "page": page,
            "total": total,
            "tickets_sum": tickets_sum,
            "total_pages": total_pages,
            "submitted": submitted,
            "orders": order_items,
            "error": error,
        },
    )


@router.get("/query", response_class=HTMLResponse)
def query_page(request: Request):
    return _render(request)


@router.post("/query", response_class=HTMLResponse)
def query_submit(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    name = name.strip()
    ip = _client_ip(request)
    allowed, retry_after = check_query_rate_limit(ip)
    if not allowed:
        return _render(request, name=name, rate_limited=True, retry_after=retry_after)

    results = query_orders_by_name(db, name)
    return _render(
        request,
        name=name,
        submitted=True,
        results=results,
        retry_after=get_query_cooldown_seconds(),
    )


@router.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request):
    return _render_orders(request)


@router.post("/orders", response_class=HTMLResponse)
def orders_submit(
    request: Request,
    api_key: str = Form(...),
    match_id: str = Form(""),
    page_size: str = Form("20"),
    page: str = Form("1"),
    db: Session = Depends(get_db),
):
    api_key = api_key.strip()
    match_id = match_id.strip()
    try:
        page_size_value = int(page_size)
    except ValueError:
        page_size_value = 20
    if page_size_value not in ORDER_PAGE_SIZES:
        page_size_value = 20
    try:
        page_value = max(1, int(page))
    except ValueError:
        page_value = 1

    if not api_key or len(api_key) > 64:
        return _render_orders(
            request,
            api_key=api_key,
            match_id=match_id,
            page_size=page_size_value,
            submitted=True,
            error="请输入有效密钥",
        )

    match_id_value: int | None = None
    if match_id:
        if not match_id.isdigit() or int(match_id) <= 0:
            return _render_orders(
                request,
                api_key=api_key,
                match_id=match_id,
                page_size=page_size_value,
                submitted=True,
                error="比赛 ID 必须是正整数",
            )
        match_id_value = int(match_id)

    result = query_orders_by_api_key(
        db,
        api_key,
        match_id=match_id_value,
        page=page_value,
        page_size=page_size_value,
    )
    return _render_orders(
        request,
        api_key=api_key,
        match_id=match_id,
        page_size=result.page_size,
        page=result.page,
        total=result.total,
        tickets_sum=result.tickets_sum,
        total_pages=result.total_pages,
        submitted=True,
        orders=result.orders,
        error="" if result.key_valid else "密钥不存在或无权查看订单",
    )
