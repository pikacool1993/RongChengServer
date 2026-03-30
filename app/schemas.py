from pydantic import BaseModel

class ConfigRequest(BaseModel):
    match_id: str

class AuthRequest(BaseModel):
    api_key: str
    device_id: str

class EventRequest(BaseModel):
    api_key: str
    device_id: str
    event: str

class AdminCreateUserRequest(BaseModel):
    password: str
    name: str
    api_key: str
    max_devices: int

class AdminCreateConfigRequest(BaseModel):
    password: str
    content: str
    match_id: int
