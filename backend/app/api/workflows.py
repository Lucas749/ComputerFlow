"""
workflows.py — Workflow CRUD endpoints.

POST /workflows/upload          Upload video + optional events file; starts compile
GET  /workflows/{id}            Return full workflow.json
PUT  /workflows/{id}            Replace workflow.json (atomic)
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session  # noqa: F401 — used by get_db dependency

from app.models import get_db
from app.store import (
    WorkflowStore,
    ensure_workflow_dirs,
    event_screenshots_dir,
    events_path,
    video_path,
)

router = APIRouter()


# ── Upload + compile ──────────────────────────────────────────────────────────

@router.post("/workflows/upload")
async def upload_workflow(
    video: UploadFile = File(...),
    events: Optional[UploadFile] = File(None),
    screenshots: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    """
    Upload an .mp4 screen recording (and optional .events.json telemetry).

    1. Generates a ``wf_`` prefixed ID.
    2. Saves files to ``data/workflows/{id}/videos/``.
    3. Inserts a Workflow row (status="compiling").
    4. Kicks off the compile pipeline as a background asyncio task.
    5. Returns ``{"id": "wf_...", "status": "compiling"}`` immediately.
    """
    workflow_id = "wf_" + secrets.token_urlsafe(8)
    ensure_workflow_dirs(workflow_id)

    # Save video
    vid_path = video_path(workflow_id)
    async with aiofiles.open(vid_path, "wb") as f:
        content = await video.read()
        await f.write(content)

    # Save events file (optional)
    ev_path: Optional[Path] = None
    if events and events.filename:
        ev_path = events_path(workflow_id)
        async with aiofiles.open(ev_path, "wb") as f:
            ev_content = await events.read()
            await f.write(ev_content)

    # Save per-event screenshots (ev_XXXX.jpg) uploaded from the Mac client.
    # These are lossless pre-action frames — the compiler prefers them over
    # ffmpeg-extracted video frames.
    shots_dir = event_screenshots_dir(workflow_id)
    for shot in screenshots or []:
        if not shot.filename:
            continue
        out = shots_dir / Path(shot.filename).name  # strip any directory
        async with aiofiles.open(out, "wb") as f:
            await f.write(await shot.read())

    # Create DB record
    store = WorkflowStore(db)
    name = Path(video.filename or "Untitled").stem.replace("_", " ").replace("-", " ").title()
    store.create_workflow(workflow_id, name=name)

    # Fire-and-forget compile task (uses its own DB session — request session closes after return)
    asyncio.create_task(
        _run_compile(workflow_id=workflow_id, name=name)
    )

    return {"id": workflow_id, "status": "compiling"}


# ── Get workflow ──────────────────────────────────────────────────────────────

@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """Return the full workflow.json for the given ID."""
    store = WorkflowStore(db)
    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    data = store.read_workflow_json(workflow_id)
    if data is None:
        # Workflow exists in DB but JSON not yet written (still compiling)
        return JSONResponse(
            content={"id": workflow_id, "status": wf.status},
            status_code=202,
        )
    return data


# ── Workflow screenshot ───────────────────────────────────────────────────────

@router.get("/workflows/{workflow_id}/screenshot/{filename}")
async def get_workflow_screenshot(workflow_id: str, filename: str):
    """Serve a per-event screenshot for a workflow (used by the review window)."""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = event_screenshots_dir(workflow_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type="image/jpeg")


# ── Update workflow ───────────────────────────────────────────────────────────

class WorkflowUpdateBody(BaseModel):
    model_config = {"extra": "allow"}  # accept the full workflow JSON object


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdateBody,
    db: Session = Depends(get_db),
):
    """
    Replace the workflow.json for the given ID (atomic write + DB update).
    Accepts the full workflow JSON as the request body.
    """
    store = WorkflowStore(db)
    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow_dict = body.model_dump()
    store.update_workflow_json(workflow_id, workflow_dict)
    return {"id": workflow_id, "status": "ready"}


# ── Background compile pipeline ───────────────────────────────────────────────

async def _run_compile(workflow_id: str, name: str) -> None:
    """Background task: compile a recorded workflow.

    Set COMPILER=claude in the environment to use Claude Sonnet instead of Lightcone.
    """
    import os
    from app.api.stream import get_compile_queue
    from app.models import SessionLocal
    from app.store import (
        WorkflowStore,
        event_screenshots_dir,
        events_path as get_events_path,
    )

    compiler_backend = os.environ.get("COMPILER", "lightcone").lower()

    if compiler_backend == "claude":
        from app.compiler.claude_vlm import compile_with_claude as compile_fn
    else:
        from app.compiler.lightcone_vlm import compile_with_lightcone as compile_fn

    queue = get_compile_queue(workflow_id)
    db = SessionLocal()
    store = WorkflowStore(db)

    loop = asyncio.get_event_loop()

    async def emit(stage: int, progress: int, subline: str, **extra) -> None:
        await queue.put(
            {"stage": stage, "progress": progress, "subline": subline, **extra}
        )

    def emit_sync(stage: int, progress: int, subline: str) -> None:
        # Called from worker thread — schedule on the loop.
        asyncio.run_coroutine_threadsafe(emit(stage, progress, subline), loop)

    try:
        await emit(0, 5, "Preparing recording…")

        ev_file = get_events_path(workflow_id)
        shots_dir = event_screenshots_dir(workflow_id)

        events_data: list[dict] = []
        if ev_file.exists():
            try:
                events_data = json.loads(ev_file.read_text(encoding="utf-8"))
            except Exception:
                events_data = []

        await emit(0, 15, "Using pre-action screenshots…")
        workflow_json = await loop.run_in_executor(
            None,
            lambda: compile_fn(
                workflow_id=workflow_id,
                events=events_data,
                screenshots_dir=shots_dir,
                name=name,
                progress_callback=emit_sync,
            ),
        )

        from app.store import workflow_json_path
        import logging, os
        store.update_workflow_json(workflow_id, workflow_json)
        saved_path = workflow_json_path(workflow_id).resolve()
        logging.getLogger("uvicorn.error").info(
            f"[ComputerFlow] workflow.json saved → {saved_path}"
        )
        await emit(3, 100, "Complete", workflowId=workflow_id)

    except Exception as exc:
        store.update_workflow_status(workflow_id, "error")
        await queue.put(
            {"stage": "error", "progress": 0, "subline": str(exc), "error": True}
        )
        raise
    finally:
        db.close()
