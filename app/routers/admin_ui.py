from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from ..database import get_db
from ..env import load_env
from ..models import Config, Device, Order, User, now_cn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-ui"])

templates = Jinja2Templates(directory=str(os.path.join(os.path.dirname(__file__), "..", "templates")))


def _require_login(request: Request) -> bool:
    return bool(request.session.get("admin_logged_in"))


def _redirect_to_login(next_path: str) -> RedirectResponse:
    return RedirectResponse(url=f"/admin-ui/login?next={next_path}", status_code=302)


@router.get("/admin-ui/login", response_class=HTMLResponse)
def login_page(request: Request, next: str | None = None):
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "next": next or "/admin-ui"},
    )


@router.post("/admin-ui/login")
def login_action(
    request: Request,
    password: str = Form(...),
    next: str = Form("/admin-ui"),
):
    load_env()
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "next": next, "error": "管理员口令未配置（ADMIN_PASSWORD）"},
            status_code=500,
        )

    if password != admin_password:
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "next": next, "error": "口令错误"},
            status_code=401,
        )

    request.session["admin_logged_in"] = True
    # 默认跳到订单页
    target = next or "/admin-ui/orders"
    if target == "/admin-ui":
        target = "/admin-ui/orders"
    return RedirectResponse(url=target, status_code=302)


@router.post("/admin-ui/logout")
def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin-ui/login", status_code=302)


@router.get("/admin-ui", response_class=HTMLResponse)
def dashboard(request: Request):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/orders")
    return RedirectResponse(url="/admin-ui/orders", status_code=302)


@router.get("/admin-ui/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/users")

    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("admin/users.html", {"request": request, "users": users})


@router.post("/admin-ui/users/create")
def users_create(
    request: Request,
    name: str = Form(""),
    api_key: str = Form(...),
    max_devices: int = Form(1),
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/users")

    existing = db.query(User).filter(User.api_key == api_key).first()
    if existing:
        existing.name = name
        existing.max_devices = max_devices
        existing.updated_at = now_cn()
        db.commit()
        return RedirectResponse(url="/admin-ui/users", status_code=302)

    u = User(name=name, api_key=api_key, max_devices=max_devices)
    db.add(u)
    db.commit()
    return RedirectResponse(url="/admin-ui/users", status_code=302)


@router.get("/admin-ui/users/{api_key}", response_class=HTMLResponse)
def users_edit_page(request: Request, api_key: str, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login(f"/admin-ui/users/{api_key}")

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return RedirectResponse(url="/admin-ui/users", status_code=302)

    return templates.TemplateResponse("admin/user_edit.html", {"request": request, "user": u})


@router.post("/admin-ui/users/{api_key}/update")
def users_update(
    request: Request,
    api_key: str,
    name: str = Form(""),
    max_devices: int = Form(1),
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        return _redirect_to_login(f"/admin-ui/users/{api_key}")

    u = db.query(User).filter(User.api_key == api_key).first()
    if u:
        u.name = name
        u.max_devices = max_devices
        u.updated_at = now_cn()
        db.commit()
    return RedirectResponse(url="/admin-ui/users", status_code=302)


@router.post("/admin-ui/users/{api_key}/delete")
def users_delete(request: Request, api_key: str, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/users")

    u = db.query(User).filter(User.api_key == api_key).first()
    if u:
        db.delete(u)
        db.commit()
    return RedirectResponse(url="/admin-ui/users", status_code=302)


@router.get("/admin-ui/users/{api_key}/devices", response_class=HTMLResponse)
def user_devices_page(request: Request, api_key: str, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login(f"/admin-ui/users/{api_key}/devices")

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return RedirectResponse(url="/admin-ui/users", status_code=302)

    devices = db.query(Device).filter(Device.user_id == u.id).order_by(Device.last_seen.desc()).all()
    return templates.TemplateResponse(
        "admin/devices.html",
        {"request": request, "user": u, "devices": devices},
    )


@router.post("/admin-ui/devices/{device_id}/delete")
def device_delete(request: Request, device_id: int, next: str = Form("/admin-ui/users"), db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login(next)

    d = db.query(Device).filter(Device.id == device_id).first()
    if d:
        db.delete(d)
        db.commit()
    return RedirectResponse(url=next or "/admin-ui/users", status_code=302)


@router.get("/admin-ui/orders", response_class=HTMLResponse)
def orders_page(
    request: Request,
    api_key: str | None = None,
    device_id: str | None = None,
    match_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        q = request.url.path
        if request.url.query:
            q = f"{q}?{request.url.query}"
        return _redirect_to_login(q)

    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 200:
        page_size = 200

    match_id_value: int | None = None
    if match_id is not None:
        match_id = match_id.strip()
        if match_id == "":
            match_id_value = None
        elif match_id.isdigit():
            match_id_value = int(match_id)
        else:
            # 非数字：当成未填写，避免直接报 422/500 影响使用
            match_id_value = None

    q = db.query(Order, User).join(User, User.id == Order.user_id)
    if api_key:
        q = q.filter(User.api_key == api_key)
    if device_id:
        q = q.filter(Order.device_id == device_id)
    if match_id_value is not None:
        q = q.filter(Order.match_id == match_id_value)

    total = q.count()
    tickets_sum = (
        db.query(func.coalesce(func.sum(Order.ticket_count), 0))
        .select_from(Order)
        .join(User, User.id == Order.user_id)
        .filter(True)
    )
    if api_key:
        tickets_sum = tickets_sum.filter(User.api_key == api_key)
    if device_id:
        tickets_sum = tickets_sum.filter(Order.device_id == device_id)
    if match_id_value is not None:
        tickets_sum = tickets_sum.filter(Order.match_id == match_id_value)
    tickets_sum_value = int(tickets_sum.scalar() or 0)

    items = (
        q.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    orders: list[dict[str, Any]] = []
    for o, u in items:
        orders.append(
            {
                "id": o.id,
                "api_key": u.api_key,
                "device_id": o.device_id,
                "match_id": o.match_id,
                "ticket_count": o.ticket_count,
                "order_names": o.order_names,
                "order_region": o.order_region,
                "order_price": o.order_price,
                "first_delay": o.first_delay,
                "first_start_t": o.first_start_t,
                "first_end_t": o.first_end_t,
                "created_at": o.created_at,
            }
        )

    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "orders": orders,
            "filters": {"api_key": api_key or "", "device_id": device_id or "", "match_id": "" if match_id_value is None else str(match_id_value)},
            "page": page,
            "page_size": page_size,
            "total": total,
            "tickets_sum": tickets_sum_value,
        },
    )


@router.post("/admin-ui/orders/{order_id}/delete")
def order_delete(request: Request, order_id: int, next: str = Form("/admin-ui/orders"), db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login(next)

    o = db.query(Order).filter(Order.id == order_id).first()
    if o:
        db.delete(o)
        db.commit()
    return RedirectResponse(url=next or "/admin-ui/orders", status_code=302)


@router.post("/admin-ui/orders/delete-all")
def orders_delete_all(request: Request, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/orders")

    db.query(Order).delete(synchronize_session=False)
    db.commit()
    return RedirectResponse(url="/admin-ui/orders", status_code=302)


# =========================
# configs（赛事/公告配置）
# =========================
@router.get("/admin-ui/configs", response_class=HTMLResponse)
def configs_page(request: Request, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/configs")

    rows = db.query(Config).order_by(Config.match_id.asc()).all()
    return templates.TemplateResponse("admin/configs.html", {"request": request, "configs": rows})


@router.post("/admin-ui/configs/create")
def configs_create(
    request: Request,
    match_id: int = Form(...),
    content: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/configs")

    text = (content or "")[:1024]
    existing = db.query(Config).filter(Config.match_id == match_id).first()
    if existing:
        existing.content = text
        db.commit()
    else:
        db.add(Config(match_id=match_id, content=text))
        db.commit()
    return RedirectResponse(url="/admin-ui/configs", status_code=302)


@router.get("/admin-ui/configs/{config_id}", response_class=HTMLResponse)
def configs_edit_page(
    request: Request,
    config_id: int,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        return _redirect_to_login(f"/admin-ui/configs/{config_id}")

    c = db.query(Config).filter(Config.id == config_id).first()
    if not c:
        return RedirectResponse(url="/admin-ui/configs", status_code=302)

    err_msg = None
    if error == "match_id_exists":
        err_msg = "该 match_id 已被其它配置占用，请换一个。"

    return templates.TemplateResponse(
        "admin/config_edit.html",
        {"request": request, "config": c, "error": err_msg},
    )


@router.post("/admin-ui/configs/{config_id}/update")
def configs_update(
    request: Request,
    config_id: int,
    match_id: int = Form(...),
    content: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        return _redirect_to_login(f"/admin-ui/configs/{config_id}")

    c = db.query(Config).filter(Config.id == config_id).first()
    if not c:
        return RedirectResponse(url="/admin-ui/configs", status_code=302)

    text = (content or "")[:1024]
    other = db.query(Config).filter(Config.match_id == match_id, Config.id != config_id).first()
    if other:
        # match_id 已被其它行占用，避免违反唯一约束
        return RedirectResponse(url=f"/admin-ui/configs/{config_id}?error=match_id_exists", status_code=302)

    c.match_id = match_id
    c.content = text
    db.commit()
    return RedirectResponse(url="/admin-ui/configs", status_code=302)


@router.post("/admin-ui/configs/{config_id}/delete")
def configs_delete(request: Request, config_id: int, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/configs")

    c = db.query(Config).filter(Config.id == config_id).first()
    if c:
        db.delete(c)
        db.commit()
    return RedirectResponse(url="/admin-ui/configs", status_code=302)


def install_session_middleware(app) -> None:
    load_env()
    secret = os.getenv("ADMIN_UI_SESSION_SECRET")
    if not secret:
        raise RuntimeError("环境变量 ADMIN_UI_SESSION_SECRET 未设置（用于后台管理 Cookie 签名）。")
    app.add_middleware(SessionMiddleware, secret_key=secret)

