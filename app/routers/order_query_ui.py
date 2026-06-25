from __future__ import annotations

import os
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.order_query import query_orders_by_name
from ..services.rate_limit_service import check_query_rate_limit, get_query_cooldown_seconds

router = APIRouter(tags=["order-query-ui"])

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
