from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from datetime import datetime

from .schemas import AuthRequest, EventRequest
from .database import SessionLocal, engine
from .models import Base, User, Device, Event
from .admin import router as admin_router
from .response import success, fail

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(admin_router)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=200,
        content=fail(msg=str(exc))
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content=fail(msg=str(exc))
    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/auth")
def auth(req: AuthRequest, db: Session = Depends(get_db)):
    api_key = req.api_key
    device_id = req.device_id

    u = db.query(User).filter_by(api_key=api_key).first()
    if not u:
        return fail(code=1, msg="unauthorized")

    device = db.query(Device).filter_by(user_id=u.id, device_id=device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=u.id).count()

        if device_count >= u.max_devices:
            return fail(code=2, msg="device limit reached")

        db.add(Device(
            user_id=u.id,
            device_id=device_id
        ))
    else:
        device.last_seen = datetime.now()

    db.commit()

    device_count = db.query(Device).filter_by(user_id=u.id).count()

    return success({
        "device_count": device_count,
        "max_devices": u.max_devices
    })

@app.post("/event")
def log_event(req: EventRequest, db: Session = Depends(get_db)):
    api_key = req.api_key
    device_id = req.device_id
    event = req.event

    u = db.query(User).filter_by(api_key=api_key).first()

    if not u:
        return fail(code=1, msg="unauthorized")

    db.add(Event(
        user_id=u.id,
        device_id=device_id,
        event_type=event
    ))
    db.commit()

    return success({})
