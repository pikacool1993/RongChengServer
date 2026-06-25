from typing import Any

from .crypto import aes_encrypt


def success(data: Any = None, msg: str = "success", encrypt: bool = True):
    body = {
        "code": 0,
        "data": data,
        "msg": msg,
    }
    if not encrypt:
        return body
    return {"payload": aes_encrypt(body)}


def fail(code: int = -1, msg: str = "fail", encrypt: bool = False):
    body = {
        "code": code,
        "data": None,
        "msg": msg,
    }
    if not encrypt:
        return body
    return {"payload": aes_encrypt(body)}


def invalid_encrypted_request():
    return fail(-4001, msg="invalid encrypted request", encrypt=False)
