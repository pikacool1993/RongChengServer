from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime

from .database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=True)
    api_key = Column(String(64), unique=True, index=True)
    max_devices = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at =Column(DateTime, default=datetime.now)

class Device(Base):
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    device_id = Column(String(128))
    first_seen = Column(DateTime, default=datetime.now)
    last_seen = Column(DateTime, default=datetime.now)

class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    device_id = Column(String(128), index=True)
    event_type = Column(String(32))
    created_at = Column(DateTime, default=datetime.now)
