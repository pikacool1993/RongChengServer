from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, inspect, text

from .database import Base


def now_cn():
    utc_plus_8 = timezone(timedelta(hours=8))
    return datetime.now(utc_plus_8).replace(tzinfo=None)


class Config(Base):
    __tablename__ = "configs"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, unique=True, index=True)
    content = Column(String(1024), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=True)
    api_key = Column(String(64), unique=True, index=True)
    lark_key = Column(String(128), nullable=True)
    max_devices = Column(Integer, default=1)
    role = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_cn)
    updated_at = Column(DateTime, default=now_cn)


class UserConfig(Base):
    __tablename__ = "user_configs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    config = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_cn)
    updated_at = Column(DateTime, default=now_cn)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    device_id = Column(String(128))
    device_name = Column(String(128), nullable=True)
    first_seen = Column(DateTime, default=now_cn)
    last_seen = Column(DateTime, default=now_cn)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    raw_api_key = Column(String(128), nullable=True, index=True)
    task_id = Column(String(128), nullable=True, index=True)
    device_id = Column(String(128), nullable=True, index=True)
    device_name = Column(String(128), nullable=True)
    order_ip = Column(String(45), nullable=True, index=True)
    order_names = Column(String(128), nullable=True)
    order_cards = Column(String(128), nullable=True)
    order_phones = Column(String(128), nullable=True)
    order_region = Column(String(128), nullable=True)
    order_price = Column(String(128), nullable=True)
    match_id = Column(Integer, nullable=True, index=True)
    ticket_count = Column(Integer, default=0)
    first_delay = Column(Integer, default=0)
    first_start_t = Column(String(128), nullable=True)
    first_end_t = Column(String(128), nullable=True)
    type = Column(Integer, default=0)
    ticket_holders_json = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    parse_status = Column(String(32), default="ok", index=True)
    parse_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_cn)


def ensure_schema_columns(engine) -> None:
    """Best-effort lightweight schema upgrade for deployments without Alembic."""
    inspector = inspect(engine)
    additions = {
        "users": {
            "lark_key": "VARCHAR(128) NULL",
            "role": "INT NULL DEFAULT 0",
        },
        "devices": {
            "device_name": "VARCHAR(128) NULL",
        },
        "orders": {
            "raw_api_key": "VARCHAR(128) NULL",
            "task_id": "VARCHAR(128) NULL",
            "device_name": "VARCHAR(128) NULL",
            "order_ip": "VARCHAR(45) NULL",
            "ticket_holders_json": "TEXT NULL",
            "raw_payload": "TEXT NULL",
            "parse_status": "VARCHAR(32) NULL DEFAULT 'ok'",
            "parse_error": "TEXT NULL",
        },
    }

    table_columns = {}
    for table in additions:
        if inspector.has_table(table):
            table_columns[table] = {col["name"] for col in inspector.get_columns(table)}

    order_indexes = set()
    if inspector.has_table("orders"):
        order_indexes = {index["name"] for index in inspector.get_indexes("orders")}

    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in table_columns:
                continue
            existing = table_columns.get(table, set())
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        if inspector.has_table("orders"):
            for index_name, column_name in {
                "ix_orders_task_id": "task_id",
                "ix_orders_order_ip": "order_ip",
            }.items():
                if index_name not in order_indexes:
                    conn.execute(text(f"CREATE INDEX {index_name} ON orders ({column_name})"))
