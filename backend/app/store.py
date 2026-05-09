"""
WorkflowStore — CRUD helpers + file-system layout for ComputerFlow workflows.

File layout under ./data/ (relative to uvicorn cwd, i.e. backend/):
  data/workflows/{id}/
    workflow.json
    videos/wf_{id}.mp4
    videos/wf_{id}.events.json
    screens/
      raw/         ← AI-selected candidate frames
      s1.png …     ← final step screenshots
    runs/{run_id}/
      inputs.json
      log.ndjson
      output/result.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Run, Workflow

# Base data directory (relative to the directory uvicorn is started from)
DATA_ROOT = Path("data")


# ── Path helpers ───────────────────────────────────────────────────────────────

def workflow_dir(workflow_id: str) -> Path:
    return DATA_ROOT / "workflows" / workflow_id


def workflow_json_path(workflow_id: str) -> Path:
    return workflow_dir(workflow_id) / "workflow.json"


def video_path(workflow_id: str) -> Path:
    return workflow_dir(workflow_id) / "videos" / f"{workflow_id}.mp4"


def events_path(workflow_id: str) -> Path:
    return workflow_dir(workflow_id) / "videos" / f"{workflow_id}.events.json"


def screens_dir(workflow_id: str) -> Path:
    return workflow_dir(workflow_id) / "screens"


def raw_frames_dir(workflow_id: str) -> Path:
    return screens_dir(workflow_id) / "raw"


def event_screenshots_dir(workflow_id: str) -> Path:
    """Per-event screenshots uploaded from the Mac client (ev_XXXX.jpg)."""
    return screens_dir(workflow_id) / "events"


def run_dir(workflow_id: str, run_id: str) -> Path:
    return workflow_dir(workflow_id) / "runs" / run_id


def run_log_path(workflow_id: str, run_id: str) -> Path:
    return run_dir(workflow_id, run_id) / "log.ndjson"


def run_result_path(workflow_id: str, run_id: str) -> Path:
    return run_dir(workflow_id, run_id) / "output" / "result.json"


def ensure_workflow_dirs(workflow_id: str) -> None:
    """Create the full directory tree for a new workflow."""
    workflow_dir(workflow_id).mkdir(parents=True, exist_ok=True)
    (workflow_dir(workflow_id) / "videos").mkdir(parents=True, exist_ok=True)
    screens_dir(workflow_id).mkdir(parents=True, exist_ok=True)
    raw_frames_dir(workflow_id).mkdir(parents=True, exist_ok=True)
    event_screenshots_dir(workflow_id).mkdir(parents=True, exist_ok=True)


def ensure_run_dirs(workflow_id: str, run_id: str) -> None:
    """Create the full directory tree for a new run."""
    (run_dir(workflow_id, run_id) / "output").mkdir(parents=True, exist_ok=True)


# ── Workflow CRUD ──────────────────────────────────────────────────────────────

class WorkflowStore:
    """
    Thin wrapper around SQLAlchemy session + disk I/O for workflows and runs.
    Instantiate per-request (or use module-level helpers with a passed session).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- Workflows --

    def create_workflow(self, workflow_id: str, name: str = "Untitled") -> Workflow:
        wf = Workflow(id=workflow_id, name=name, status="compiling")
        self.db.add(wf)
        self.db.commit()
        self.db.refresh(wf)
        return wf

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self.db.query(Workflow).filter(Workflow.id == workflow_id).first()

    def update_workflow_status(self, workflow_id: str, status: str) -> None:
        self.db.query(Workflow).filter(Workflow.id == workflow_id).update(
            {"status": status}
        )
        self.db.commit()

    def update_workflow_json(self, workflow_id: str, workflow_json: dict) -> None:
        """Atomically persist workflow JSON to disk and update the DB record."""
        path = workflow_json_path(workflow_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(workflow_json, indent=2), encoding="utf-8")

        self.db.query(Workflow).filter(Workflow.id == workflow_id).update(
            {
                "json": json.dumps(workflow_json),
                "name": workflow_json.get("name", "Untitled"),
                "status": "ready",
            }
        )
        self.db.commit()

    def read_workflow_json(self, workflow_id: str) -> Optional[dict]:
        """Read workflow.json from disk (preferred) or fall back to DB blob."""
        path = workflow_json_path(workflow_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        wf = self.get_workflow(workflow_id)
        if wf and wf.json:
            return json.loads(wf.json)
        return None

    # -- Runs --

    def create_run(
        self,
        run_id: str,
        workflow_id: str,
        inputs: Optional[list] = None,
    ) -> Run:
        from datetime import datetime

        run = Run(
            id=run_id,
            workflow_id=workflow_id,
            status="pending",
            started_at=datetime.utcnow(),
            inputs_json=json.dumps(inputs) if inputs is not None else None,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_run(self, run_id: str) -> Optional[Run]:
        return self.db.query(Run).filter(Run.id == run_id).first()

    def update_run(self, run_id: str, **fields) -> None:
        self.db.query(Run).filter(Run.id == run_id).update(fields)
        self.db.commit()

    def finish_run(
        self,
        run_id: str,
        status: str,
        output: Optional[dict] = None,
        environment_id: Optional[str] = None,
    ) -> None:
        from datetime import datetime

        updates: dict = {
            "status": status,
            "finished_at": datetime.utcnow(),
        }
        if output is not None:
            updates["output_json"] = json.dumps(output)
        if environment_id is not None:
            updates["environment_id"] = environment_id
        self.db.query(Run).filter(Run.id == run_id).update(updates)
        self.db.commit()
