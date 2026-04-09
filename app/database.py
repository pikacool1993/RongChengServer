import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from .env import load_env

load_env()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "环境变量 DATABASE_URL 未设置。请在本机/容器环境中设置它，例如：\n"
        'Windows PowerShell:  $env:DATABASE_URL="mysql+pymysql://root:123456@localhost:3306/rc_db"\n'
        'Docker Compose:     在 docker-compose.yml 或 .env 中设置 DATABASE_URL\n'
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# =========================
# FastAPI 依赖，用于请求中获取 db
# =========================
def get_db() -> Session:
    """
        在 FastAPI 路由中使用：
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()