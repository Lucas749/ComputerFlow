"""
ComputerFlow FastAPI application entry point.

How to run:
    cd /Users/lucas/Desktop/VibeCode/ComputerFlow/backend
    pip install -e ".[dev]"
    uvicorn app.main:app --reload --port 8000

The SQLite database is created at ./data/computerflow.db on first start.
Workflow files are stored under ./data/workflows/{id}/.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from the project root (two levels above backend/app/)
load_dotenv(Path(__file__).parents[2] / ".env")

from app.models import Base, engine  # noqa: E402 — must come after load_dotenv


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os, logging
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)
    compiler = os.environ.get("COMPILER", "lightcone").lower()
    logging.getLogger("uvicorn.error").info(
        f"[ComputerFlow] Compiler backend: {'Claude Sonnet 4.6' if compiler == 'claude' else 'Lightcone Northstar'}"
    )
    yield


app = FastAPI(
    title="ComputerFlow API",
    version="0.1.0",
    description="Record macOS screens, compile into executable SOPs via Claude VLM, run on cloud infra.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

from app.api.workflows import router as workflows_router  # noqa: E402
from app.api.runs import router as runs_router            # noqa: E402
from app.api.stream import router as stream_router        # noqa: E402

app.include_router(workflows_router)
app.include_router(runs_router)
app.include_router(stream_router)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
