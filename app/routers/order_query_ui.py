from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.order_query import load_match_info, query_orders_by_name

router = APIRouter(tags=["order-query-ui"])

templates = Jinja2Templates(directory=str(os.path.join(os.path.dirname(__file__), "..", "templates")))


def _render(
    request: Request,
    *,
    name: str = "",
    submitted: bool = False,
    results: list[dict[str, str | None]] | None = None,
):
    match_info = load_match_info()
    return templates.TemplateResponse(
        "query.html",
        {
            "request": request,
            "match_info": match_info,
            "name": name,
            "submitted": submitted,
            "results": results,
        },
    )


@router.get("/query", response_class=HTMLResponse)
def query_page(request: Request):
    return _render(request)


@router.post("/query", response_class=HTMLResponse)
def query_submit(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    name = name.strip()
    results = query_orders_by_name(db, name)
    return _render(request, name=name, submitted=True, results=results)
