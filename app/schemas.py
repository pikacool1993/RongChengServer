from pydantic import BaseModel

class AuthRequest(BaseModel):
    api_key: str
    device_id: str

class TaskCreateRequest(BaseModel):
    api_key: str
    device_id: str
    match_id: int

class TaskUpdateRequest(BaseModel):
    api_key: str
    task_id: int
    status: int
    ticket_count: int

class AdminCreateUserRequest(BaseModel):
    password: str
    name: str
    api_key: str
    max_devices: int

class AdminCreateConfigRequest(BaseModel):
    password: str
    content: str
    match_id: int
