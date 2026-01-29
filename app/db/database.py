import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .tunnel import tunnel
from .query_loader import query_loader

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:{tunnel.local_port}/{os.getenv('DB_NAME')}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()