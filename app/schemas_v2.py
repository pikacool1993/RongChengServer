from __future__ import annotations

from ipaddress import ip_address
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator


class V2Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class EncryptedEnvelopeV2(V2Model):
    payload: str = Field(min_length=1)


class AuthV2Request(V2Model):
    api_key: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, max_length=128)


class TaskCheckV2Request(V2Model):
    api_key: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, max_length=128)


class MatchConfigV2Request(V2Model):
    api_key: str | None = Field(default=None, max_length=64)


class MatchDetailV2Request(V2Model):
    api_key: str = Field(min_length=1, max_length=64)
    match_id: PositiveInt


class TicketHolderV2(V2Model):
    name: str = Field(min_length=1, max_length=128)
    phone: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    price: str | None = Field(default=None, max_length=128)

    @field_validator("name", "phone", "region", "price", mode="before")
    @classmethod
    def stringify_scalar(cls, value: Any) -> Any:
        if value is None or isinstance(value, str):
            return value
        return str(value)


class OrderUploadV2Request(V2Model):
    api_key: str = Field(min_length=1, max_length=64)
    task_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, max_length=128)
    order_ip: str = Field(min_length=1, max_length=45)
    match_id: PositiveInt | None = None
    ticket_count: int | None = Field(default=None, ge=0)
    ticket_holders: list[TicketHolderV2] = Field(
        default_factory=list,
        validation_alias=AliasChoices("ticket_holders", "tickets"),
        max_length=20,
    )
    first_delay: int = Field(default=0, ge=0)
    task_type: Literal[0, 1, 2, 3] = Field(
        default=0,
        validation_alias=AliasChoices("task_type", "type"),
    )

    @field_validator("task_id", mode="before")
    @classmethod
    def stringify_task_id(cls, value: Any) -> Any:
        if value is None or isinstance(value, str):
            return value
        return str(value)

    @field_validator("order_ip", mode="before")
    @classmethod
    def validate_order_ip(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("order_ip must be an IPv4 or IPv6 address")
        try:
            return str(ip_address(value.strip()))
        except ValueError as exc:
            raise ValueError("order_ip must be an IPv4 or IPv6 address") from exc

    @model_validator(mode="after")
    def fill_ticket_count(self) -> "OrderUploadV2Request":
        if self.ticket_count is None:
            self.ticket_count = len(self.ticket_holders)
        return self


class AdminUserCreateV2Request(V2Model):
    name: str = Field(min_length=1, max_length=32)
    api_key: str = Field(min_length=1, max_length=64)
    lark_key: str | None = Field(default=None, max_length=128)
    max_devices: PositiveInt = 1
    role: Literal[0, 1] = 0


class AdminUserPatchV2Request(V2Model):
    name: str | None = Field(default=None, max_length=32)
    lark_key: str | None = Field(default=None, max_length=128)
    max_devices: PositiveInt | None = None
    role: Literal[0, 1] | None = None


class AdminUserConfigV2Request(V2Model):
    config: dict[str, Any] | None = None


class MatchNoticeV2Request(V2Model):
    content: str = Field(default="", max_length=1024)
