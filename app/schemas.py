from pydantic import BaseModel

class OrderQueryRequest(BaseModel):
    name: str

class MatchQueryRequest(BaseModel):
    api_key: str
    match_id: str

class EncryptedRequest(BaseModel):
    payload: str

class AuthRequest(BaseModel):
    api_key: str
    device_id: str
    device_name: str | None = None

class TaskCheckRequest(BaseModel):
    api_key: str
    device_id: str

class TaskOrderRequest(BaseModel):
    api_key: str | None = None
    device_id: str | None = None
    match_id: int | None = None
    ticket_count: int | None = None
    order_names: str | None = None
    order_cards: str | None = None
    order_phones: str | None = None
    order_region: str | None = None
    order_price: str | None = None
    first_delay: int | None = None
    first_start_t: str | None = None
    first_end_t: str | None = None
    type: int | None = None

class AdminCreateUserRequest(BaseModel):
    password: str
    name: str
    api_key: str
    lark_key: str | None = None
    max_devices: int
    role: int = 0

class AdminUpdateUserRequest(BaseModel):
    password: str
    api_key: str
    name: str | None = None
    lark_key: str | None = None
    max_devices: int | None = None
    role: int | None = None

class AdminCreateConfigRequest(BaseModel):
    password: str
    content: str
    match_id: int

class AdminUpsertUserConfigRequest(BaseModel):
    password: str
    api_key: str
    config: str | None = None
