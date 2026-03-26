from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from .database import SessionLocal, engine
from .models import Base, User, Device, Event
from .admin import router as admin_router

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(admin_router)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/auth")
def auth(api_key: str, device_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(api_key=api_key).first()

    if not user:
        return {"authorized": False}

    device = db.query(Device).filter_by(user_id=user.id, device_id=device_id).first()

    if not device:
        device_count = db.query(Device).filter_by(user_id=user.id).count()

        if device_count >= user.max_devices:
            return {"authorized": False,
                    "reason": "device limit reached"}

        device = Device(user_id=user.id, device_id=device_id)
        db.add(device)
    else:
        device.last_seen = datetime.now()

    db.commit()

    device_count = db.query(Device).filter_by(user_id=user.id).count()

    return {
        "authorized": True,
        "device_count": device_count,
        "max_devices": user.max_devices
    }

@app.post("/event")
def log_event(api_key: str, device_id: str, event: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(api_key=api_key).first()

    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")

    db.add(Event(
        user_id=user.id,
        device_id=device_id,
        event_type=event
    ))
    db.commit()

    return {"ok": True}
