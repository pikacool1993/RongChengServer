from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from ..crypto import EncryptedRequestError, decrypt_envelope
from ..response import invalid_encrypted_request


async def read_encrypted_request(request: Request) -> tuple[dict | None, str | None, JSONResponse | None]:
    try:
        body = await request.json()
        data, raw = decrypt_envelope(body)
        return data, raw, None
    except (EncryptedRequestError, ValueError, TypeError):
        return None, None, JSONResponse(content=invalid_encrypted_request(), status_code=400)
