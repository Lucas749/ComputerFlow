"""
SQLAlchemy models for ComputerFlow.

Tables:
  workflows  — compiled SOPs (status: compiling | ready | error)
  runs       — execution records for a workflow

Engine is SQLite with check_same_thread=False (sync, simple).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load .env from the project root (two levels up from backend/app/)
load_dotenv(Path(__file__).parents[2] / ".env")

_DB_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///./data/computerflow.db",
)

engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True)                       # "wf_" + nanoid
    name = Column(String, default="Untitled")
    json = Column(Text)                                          # full workflow JSON blob
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String, default="compiling")                 # compiling | ready | error


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.id"))
    status = Column(String, default="pending")                   # pending | running | paused | completed | error
    started_at = Column(DateTime)
    finished_at = Column(DateTime, nullable=True)
    inputs_json = Column(Text, nullable=True)                    # JSON array of input dicts
    output_json = Column(Text, nullable=True)
    live_view_url = Column(String, nullable=True)
    environment_id = Column(String, nullable=True)


def get_db():
    """FastAPI dependency: yields a DB session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
