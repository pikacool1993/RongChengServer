from typing import Any

def success(data: Any = None, msg: str = "success"):
    return {
        "code": 0,
        "data": data,
        "msg": msg
    }

def fail(code: int = -1, msg: str = "fail"):
    return {
        "code": code,
        "data": None,
        "msg": msg
    }
