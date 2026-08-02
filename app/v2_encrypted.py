from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .crypto import EncryptedRequestError, aes_encrypt, decrypt_envelope
from .schemas_v2 import EncryptedEnvelopeV2


PayloadT = TypeVar("PayloadT", bound=BaseModel)


class V2InvalidEncryptedRequest(Exception):
    pass


class V2PayloadValidationError(Exception):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("invalid request")
        self.errors = errors


class V2ClientError(Exception):
    def __init__(self, status_code: int, code: int, msg: str) -> None:
        super().__init__(msg)
        self.status_code = status_code
        self.code = code
        self.msg = msg


def decode_v2_payload(
    envelope: EncryptedEnvelopeV2,
    payload_type: type[PayloadT],
) -> tuple[PayloadT, str]:
    try:
        data, raw = decrypt_envelope(envelope.model_dump())
    except EncryptedRequestError as exc:
        raise V2InvalidEncryptedRequest from exc

    try:
        payload = payload_type.model_validate(data)
    except ValidationError as exc:
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        raise V2PayloadValidationError(errors) from exc
    return payload, raw


def encrypted_v2_body(code: int, msg: str, data: Any = None) -> dict[str, str]:
    return {
        "payload": aes_encrypt(
            {
                "code": code,
                "data": data,
                "msg": msg,
            }
        )
    }
