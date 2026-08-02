from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def v2_success(data: Any = None, msg: str = "success") -> dict[str, Any]:
    return {"code": 0, "data": data, "msg": msg}


def v2_error(
    status_code: int,
    code: int,
    msg: str,
    data: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "data": data, "msg": msg},
        headers=headers,
    )
