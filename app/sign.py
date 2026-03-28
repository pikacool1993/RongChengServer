import hashlib
import json
from typing import Dict, Any

SECRET = "my_secret_key"

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