from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL = os.environ.get("DB_URL") or f"sqlite:////opt/ingest-admin/ingest.db"

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, future=True)

def get_session():
    return SessionLocal()

