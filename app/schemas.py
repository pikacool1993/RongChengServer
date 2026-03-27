from pydantic import BaseModel

class AuthRequest(BaseModel):
    api_key: str
    device_id: str

class EventRequest(BaseModel):
    api_key: str
    device_id: str
    event: str

class AdminCreateUserRequest(BaseModel):
    name: str
    api_key: str
    max_devices: int
