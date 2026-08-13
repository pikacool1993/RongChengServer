from __future__ import annotations

import logging
import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from ..database import get_db
from ..env import load_env
from ..models import ClientTask, Config, Device, Order, User, UserConfig, now_cn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-ui"])

templates = Jinja2Templates(directory=str(os.path.join(os.path.dirname(__file__), "..", "templates")))


def _normalize_role(role: int | None) -> int:
    return 1 if role == 1 else 0


def _normalize_config_text(config: str | None) -> str:
    config_text = (config or "").strip()
    if config_text:
        json.loads(config_text)
    return config_text


def _format_config_text(config_text: str | None) -> str:
    if not config_text:
        return ""
    try:
        return json.dumps(json.loads(config_text), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return config_text


def _upsert_user_config(db: Session, user: User, config_text: str) -> None:
    row = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if row:
        row.config = config_text
        row.updated_at = now_cn()
    elif config_text:
        db.add(UserConfig(user_id=user.id, config=config_text))


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


def _live_task_groups(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(ClientTask, User, Device)
        .join(User, User.id == ClientTask.user_id)
        .join(
            Device,
            (Device.user_id == ClientTask.user_id) & (Device.device_id == ClientTask.device_id),
        )
        .order_by(User.id.asc(), Device.id.asc(), ClientTask.created_at.asc())
        .all()
    )
    user_groups: dict[int, dict[str, Any]] = {}
    device_groups: dict[tuple[int, int], dict[str, Any]] = {}
    for task, user, device in rows:
        user_group = user_groups.setdefault(
            user.id,
            {
                "user_id": user.id,
                "name": user.name or "",
                "api_key": user.api_key,
                "task_count": 0,
                "devices": [],
            },
        )
        device_key = (user.id, device.id)
        device_group = device_groups.get(device_key)
        if not device_group:
            device_group = {
                "id": device.id,
                "device_id": device.device_id,
                "device_name": device.device_name or "",
                "task_count": 0,
                "tasks": [],
            }
            device_groups[device_key] = device_group
            user_group["devices"].append(device_group)

        device_group["tasks"].append(
            {
                "task_id": task.task_id,
                "status": task.status,
                "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M:%S") if task.updated_at else "",
            }
        )
        device_group["task_count"] += 1
        user_group["task_count"] += 1
    return list(user_groups.values())


@router.get("/admin-ui/live-tasks", response_class=HTMLResponse)
def live_tasks_page(request: Request, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/live-tasks")
    return templates.TemplateResponse(
        "admin/live_tasks.html",
        {"request": request, "groups": _live_task_groups(db)},
    )


@router.get("/admin-ui/live-tasks/data")
def live_tasks_data(request: Request, db: Session = Depends(get_db)):
    if not _require_login(request):
        return JSONResponse(status_code=401, content={"detail": "not authenticated"})
    return {"groups": _live_task_groups(db)}


@router.get("/admin-ui/users", response_class=HTMLResponse)
def users_page(request: Request, error: str | None = None, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/users")

    users = db.query(User).order_by(User.created_at.desc()).all()
    user_ids = [u.id for u in users]
    config_map: dict[int, str] = {}
    if user_ids:
        rows = db.query(UserConfig).filter(UserConfig.user_id.in_(user_ids)).all()
        config_map = {row.user_id: row.config or "" for row in rows}

    err_msg = "配置必须是合法 JSON。" if error == "invalid_json" else None
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users, "config_map": config_map, "error": err_msg},
    )


@router.post("/admin-ui/users/create")
def users_create(
    request: Request,
    name: str = Form(""),
    api_key: str = Form(...),
    lark_key: str = Form(""),
    max_devices: int = Form(1),
    role: int = Form(0),
    config: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/users")

    try:
        config_text = _normalize_config_text(config)
    except json.JSONDecodeError:
        return RedirectResponse(url="/admin-ui/users?error=invalid_json", status_code=302)

    existing = db.query(User).filter(User.api_key == api_key).first()
    if existing:
        existing.name = name
        existing.lark_key = lark_key or None
        existing.max_devices = max_devices
        existing.role = _normalize_role(role)
        existing.updated_at = now_cn()
        _upsert_user_config(db, existing, config_text)
        db.commit()
        return RedirectResponse(url="/admin-ui/users", status_code=302)

    u = User(
        name=name,
        api_key=api_key,
        lark_key=lark_key or None,
        max_devices=max_devices,
        role=_normalize_role(role),
    )
    db.add(u)
    db.flush()
    _upsert_user_config(db, u, config_text)
    db.commit()
    return RedirectResponse(url="/admin-ui/users", status_code=302)


@router.get("/admin-ui/users/{api_key}", response_class=HTMLResponse)
def users_edit_page(request: Request, api_key: str, error: str | None = None, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login(f"/admin-ui/users/{api_key}")

    u = db.query(User).filter(User.api_key == api_key).first()
    if not u:
        return RedirectResponse(url="/admin-ui/users", status_code=302)

    row = db.query(UserConfig).filter(UserConfig.user_id == u.id).first()
    err_msg = "配置必须是合法 JSON。" if error == "invalid_json" else None
    return templates.TemplateResponse(
        "admin/user_edit.html",
        {
            "request": request,
            "user": u,
            "config": _format_config_text(row.config if row else ""),
            "error": err_msg,
        },
    )


@router.post("/admin-ui/users/{api_key}/update")
def users_update(
    request: Request,
    api_key: str,
    name: str = Form(""),
    lark_key: str = Form(""),
    max_devices: int = Form(1),
    role: int = Form(0),
    config: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _require_login(request):
        return _redirect_to_login(f"/admin-ui/users/{api_key}")

    try:
        config_text = _normalize_config_text(config)
    except json.JSONDecodeError:
        return RedirectResponse(url=f"/admin-ui/users/{api_key}?error=invalid_json", status_code=302)

    u = db.query(User).filter(User.api_key == api_key).first()
    if u:
        u.name = name
        u.lark_key = lark_key or None
        u.max_devices = max_devices
        u.role = _normalize_role(role)
        u.updated_at = now_cn()
        _upsert_user_config(db, u, config_text)
        db.commit()
    return RedirectResponse(url="/admin-ui/users", status_code=302)


@router.post("/admin-ui/users/{api_key}/delete")
def users_delete(request: Request, api_key: str, db: Session = Depends(get_db)):
    if not _require_login(request):
        return _redirect_to_login("/admin-ui/users")

    u = db.query(User).filter(User.api_key == api_key).first()
    if u:
        db.query(ClientTask).filter(ClientTask.user_id == u.id).delete(synchronize_session=False)
        db.query(UserConfig).filter(UserConfig.user_id == u.id).delete(synchronize_session=False)
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
        db.query(ClientTask).filter(
            ClientTask.user_id == d.user_id,
            ClientTask.device_id == d.device_id,
        ).delete(synchronize_session=False)
        db.delete(d)
        db.commit()
    return RedirectResponse(url=next or "/admin-ui/users", status_code=302)


@router.get("/admin-ui/orders", response_class=HTMLResponse)
def orders_page(
    request: Request,
    api_key: str | None = None,
    raw_api_key: str | None = None,
    device_id: str | None = None,
    device_name: str | None = None,
    match_id: str | None = None,
    parse_status: str | None = None,
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

    q = db.query(Order, User).outerjoin(User, User.id == Order.user_id)
    if api_key:
        q = q.filter(User.api_key == api_key)
    if raw_api_key:
        q = q.filter(Order.raw_api_key == raw_api_key)
    if device_id:
        q = q.filter(Order.device_id == device_id)
    if device_name:
        q = q.filter(Order.device_name.like(f"%{device_name}%"))
    if match_id_value is not None:
        q = q.filter(Order.match_id == match_id_value)
    if parse_status:
        q = q.filter(Order.parse_status == parse_status)

    ordered_items = (
        q
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
    deduped_items = []
    seen_order_cards: set[str] = set()
    for o, u in ordered_items:
        order_cards = (o.order_cards or "").strip()
        if order_cards:
            if order_cards in seen_order_cards:
                continue
            seen_order_cards.add(order_cards)
        deduped_items.append((o, u))

    total = len(deduped_items)
    tickets_sum_value = sum((o.ticket_count or 0) for o, _ in deduped_items)
    items = deduped_items[(page - 1) * page_size: page * page_size]

    device_keys = [(o.user_id, o.device_id) for o, _ in items if o.device_id]
    device_id_map: dict[tuple[int, str], int] = {}
    if device_keys:
        user_ids = {user_id for user_id, _ in device_keys}
        raw_device_ids = {raw_device_id for _, raw_device_id in device_keys}
        devices = (
            db.query(Device)
            .filter(Device.user_id.in_(user_ids), Device.device_id.in_(raw_device_ids))
            .all()
        )
        device_id_map = {(d.user_id, d.device_id): d.id for d in devices}

    orders: list[dict[str, Any]] = []
    for o, u in items:
        orders.append(
            {
                "id": o.id,
                "api_key": u.api_key if u else None,
                "raw_api_key": o.raw_api_key,
                "has_user": u is not None,
                "device_id": o.device_id,
                "device_name": o.device_name,
                "task_id": o.task_id,
                "order_ip": o.order_ip,
                "device_unique_id": device_id_map.get((o.user_id, o.device_id)) if o.device_id else None,
                "match_id": o.match_id,
                "type": o.type,
                "type_label": {0: "首开", 1: "捡漏", 2: "广播", 3: "蹲坑"}.get(o.type, f"未知({o.type})"),
                "ticket_count": o.ticket_count,
                "order_names": o.order_names,
                "order_cards": o.order_cards,
                "order_phones": o.order_phones,
                "order_region": o.order_region,
                "order_price": o.order_price,
                "first_delay": o.first_delay,
                "first_start_t": o.first_start_t,
                "first_end_t": o.first_end_t,
                "raw_payload": o.raw_payload,
                "parse_status": o.parse_status,
                "parse_error": o.parse_error,
                "created_at": o.created_at,
            }
        )

    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "orders": orders,
            "filters": {
                "api_key": api_key or "",
                "raw_api_key": raw_api_key or "",
                "device_id": device_id or "",
                "device_name": device_name or "",
                "match_id": "" if match_id_value is None else str(match_id_value),
                "parse_status": parse_status or "",
            },
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

