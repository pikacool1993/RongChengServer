import json
import base64
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .env import load_env

load_env()

def _must_get_bytes(name: str) -> bytes:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"环境变量 {name} 未设置。")
    return val.encode("utf-8")


# 约定：直接用 UTF-8 字符串作为 key/iv（长度必须匹配 AES 要求）
AES_KEY = _must_get_bytes("AES_KEY")
AES_IV = _must_get_bytes("AES_IV")

if len(AES_KEY) not in (16, 24, 32):
    raise RuntimeError(
        f"AES_KEY 长度不合法：{len(AES_KEY)}。必须是 16/24/32 字节（对应 AES-128/192/256）。"
    )
if len(AES_IV) != 16:
    raise RuntimeError(f"AES_IV 长度不合法：{len(AES_IV)}。必须是 16 字节（CBC IV）。")

def aes_encrypt(data: dict) -> str:
    """
    dict -> AES -> base64
    """
    raw = json.dumps(data, separators=(",", ":")).encode()
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    encrypted = cipher.encrypt(pad(raw, AES.block_size))
    return base64.b64encode(encrypted).decode()

def aes_decrypt(text: str) -> dict:
    encrypted = base64.b64decode(text)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
    return json.loads(decrypted.decode())
