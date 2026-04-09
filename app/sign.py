import hashlib
import json
import os
from typing import Dict, Any

from .env import load_env

load_env()

SECRET = os.getenv("SIGN_SECRET")
if not SECRET:
    raise RuntimeError(
        "环境变量 SIGN_SECRET 未设置。请设置签名密钥（建议 >= 16 位随机字符串）。"
    )

def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def sort_json(data: Dict[str, Any]) -> str:
    """
    将 JSON 排序后拼接为 key=value&key=value
    """
    items = sorted(data.items(), key=lambda x: x[0])
    return "&".join(f"{k}={v}" for k, v in items)

def generate_sign(body: Dict[str, Any], timestamp: str) -> str:
    base = sort_json(body) + timestamp + SECRET
    return md5(base)