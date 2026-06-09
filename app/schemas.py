from pydantic import BaseModel

class MatchQueryRequest(BaseModel):
    api_key: str
    match_id: str

class AuthRequest(BaseModel):
    api_key: str
    device_id: str

class TaskCheckRequest(BaseModel):
    api_key: str
    device_id: str

class TaskOrderRequest(BaseModel):
    api_key: str
    device_id: str
    match_id: int
    ticket_count: int
    order_names: str
    order_cards: str
    order_phones: str
    order_region: str
    order_price: str
    first_delay: int
    first_start_t: str
    first_end_t: str
    type: int

class AdminCreateUserRequest(BaseModel):
    password: str
    name: str
    api_key: str
    max_devices: int

class AdminUpdateUserRequest(BaseModel):
    password: str
    api_key: str
    name: str | None = None
    max_devices: int | None = None

class AdminCreateConfigRequest(BaseModel):
    password: str
    content: str
    match_id: int
