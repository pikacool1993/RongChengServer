from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from datetime import datetime, timezone, timedelta

from .database import Base

def now_cn():
    utc_plus_8 = timezone(timedelta(hours=8))
    return datetime.now(utc_plus_8).replace(tzinfo=None)

class Config(Base):
    __tablename__ = 'configs'

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, unique=True, index=True)
    content = Column(String(1024), nullable=True)

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=True)
    api_key = Column(String(64), unique=True, index=True)
    max_devices = Column(Integer, default=1)
    created_at = Column(DateTime, default=now_cn)
    updated_at =Column(DateTime, default=now_cn)

class Device(Base):
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    device_id = Column(String(128))
    first_seen = Column(DateTime, default=now_cn)
    last_seen = Column(DateTime, default=now_cn)

class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    device_id = Column(String(128), index=True)
    order_names = Column(String(128), nullable=True)
    order_cards = Column(String(128), nullable=True)
    order_phones = Column(String(128), nullable=True)
    order_region = Column(String(128), nullable=True)
    order_price = Column(String(128), nullable=True)
    match_id = Column(Integer, index=True)
    ticket_count = Column(Integer, default=0)
    first_delay = Column(Integer, default=0)
    first_start_t = Column(String(128), nullable=True)
    first_end_t = Column(String(128), nullable=True)
    type = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_cn)

