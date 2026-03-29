import json
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# AES-256 + 16字节IV
AES_KEY = b"b8c3f2e9a6d47c5b1e9032f4d8a1c6e2"
AES_IV  = b"9d4a1f7c2e6b8a03"

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
