from typing import Any

from .crypto import aes_encrypt

def success(data: Any = None, msg: str = "success"):
    encrypted = aes_encrypt(data if data is not None else {})
    return {
        "code": 0,
        "data": encrypted,
        "msg": msg
    }

def fail(code: int = -1, msg: str = "fail"):
    return {
        "code": code,
        "data": None,
        "msg": msg
    }
