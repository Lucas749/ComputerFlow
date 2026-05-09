"""
runs.py — Run management endpoints.

POST /workflows/{id}/run      Start a new run
POST /runs/{id}/control       Pause / resume / stop / take_control
"""

from __future__ import annotations

import asyncio
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import get_db
from app.store import WorkflowStore, ensure_run_dirs

router = APIRouter()


# ── Request models ─────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    inputs: Optional[list[dict[str, Any]]] = None   # [{"VarName": "value"}, ...]
    stepId: Optional[str] = None                     # run a single step only


class ControlRequest(BaseModel):
    action: str  # take_control | pause | resume | stop


# ── POST /workflows/{id}/run ──────────────────────────────────────────────────

@router.post("/workflows/{workflow_id}/run")
async def start_run(
    workflow_id: str,
    body: RunRequest = RunRequest(),
    db: Session = Depends(get_db),
):
    """
    Start executing a workflow (or a single step).

    1. Verifies the workflow exists and is ready.
    2. Creates a Run row (status="pending").
    3. Launches the execution as a background asyncio task.
    4. Returns ``{"runId": "run_...", "status": "pending"}`` immediately.
    """
    store = WorkflowStore(db)

    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow_json = store.read_workflow_json(workflow_id)
    if workflow_json is None:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow is still {wf.status} — try again later",
        )

    run_id = "run_" + secrets.token_urlsafe(8)
    ensure_run_dirs(workflow_id, run_id)
    store.create_run(run_id, workflow_id, inputs=body.inputs)

    # Pre-create the run queue so the WS endpoint can subscribe immediately
    from app.execution.run_manager import get_run_queue
    get_run_queue(run_id)

    # Launch execution in background
    asyncio.create_task(
        _run_workflow(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_json=workflow_json,
            inputs=body.inputs,
            step_id=body.stepId,
            db=db,
        )
    )

    return {"runId": run_id, "status": "pending"}


# ── POST /runs/{id}/control ───────────────────────────────────────────────────

@router.post("/runs/{run_id}/control")
async def control_run(
    run_id: str,
    body: ControlRequest,
    db: Session = Depends(get_db),
):
    """
    Send a control signal to an active run.

    Actions:
      take_control  — pause automated execution so the human can take over
      pause         — pause execution after the current step
      resume        — resume a paused run
      stop          — terminate the run immediately
    """
    store = WorkflowStore(db)
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    action = body.action
    if action == "take_control":
        store.update_run(run_id, status="paused")
    elif action == "pause":
        store.update_run(run_id, status="paused")
    elif action == "resume":
        if run.status != "paused":
            raise HTTPException(status_code=409, detail="Run is not paused")
        store.update_run(run_id, status="running")
    elif action == "stop":
        store.update_run(run_id, status="error")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action!r}")

    return {"runId": run_id, "action": action, "status": run.status}


# ── Background execution wrapper ──────────────────────────────────────────────

async def _run_workflow(
    run_id: str,
    workflow_id: str,
    workflow_json: dict,
    inputs: Optional[list],
    step_id: Optional[str],
    db: Session,
) -> None:
    from app.execution.run_manager import execute_workflow

    await execute_workflow(
        run_id=run_id,
        workflow_id=workflow_id,
        workflow=workflow_json,
        inputs=inputs,
        step_id=step_id,
        db=db,
    )
