from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.order_query import query_orders_by_name

router = APIRouter(tags=["order-query-ui"])

templates = Jinja2Templates(directory=str(os.path.join(os.path.dirname(__file__), "..", "templates")))

QUERY_COOLDOWN_SECONDS = 30
_last_query_at: dict[str, float] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit_status(ip: str) -> tuple[bool, int]:
    now = time.time()
    last = _last_query_at.get(ip, 0)
    elapsed = now - last
    if elapsed < QUERY_COOLDOWN_SECONDS:
        return False, int(QUERY_COOLDOWN_SECONDS - elapsed) + 1
    return True, 0


def _mark_query(ip: str) -> None:
    _last_query_at[ip] = time.time()


def _render(
    request: Request,
    *,
    name: str = "",
    submitted: bool = False,
    results: list[dict[str, str | None]] | None = None,
    rate_limited: bool = False,
    retry_after: int = 0,
):
    _, cooldown_remaining = _rate_limit_status(_client_ip(request))
    return templates.TemplateResponse(
        "query.html",
        {
            "request": request,
            "name": name,
            "submitted": submitted,
            "results": results,
            "rate_limited": rate_limited,
            "retry_after": retry_after or cooldown_remaining,
            "cooldown_seconds": QUERY_COOLDOWN_SECONDS,
        },
    )


@router.get("/query", response_class=HTMLResponse)
def query_page(request: Request):
    return _render(request)


@router.post("/query", response_class=HTMLResponse)
def query_submit(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    name = name.strip()
    ip = _client_ip(request)
    allowed, retry_after = _rate_limit_status(ip)
    if not allowed:
        return _render(request, name=name, rate_limited=True, retry_after=retry_after)

    _mark_query(ip)
    results = query_orders_by_name(db, name)
    return _render(request, name=name, submitted=True, results=results)
