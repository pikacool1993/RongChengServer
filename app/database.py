from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# DATABASE_URL = "mysql+pymysql://root:123456@db:3306/rc_db"
DATABASE_URL = "mysql+pymysql://root:123456@localhost:3306/rc_db"

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