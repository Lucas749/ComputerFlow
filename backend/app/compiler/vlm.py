"""
vlm.py — VLM SOP generation: selected frames → workflow.json dict.

compile_to_workflow():
  Sends the selected frames to Claude claude-sonnet-4-6 using forced tool_use
  (emit_workflow tool) to guarantee structured JSON output.
  Calls the optional progress_callback at each stage.

build_workflow_json():
  Merges the VLM output dict with the required workflow envelope fields.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable

import anthropic

from app.compiler.prompts import SYSTEM_PROMPT

# Tool definition — forces Claude to return structured workflow data
_EMIT_TOOL: dict = {
    "name": "emit_workflow",
    "description": "Emit the compiled workflow JSON",
    "input_schema": {
        "type": "object",
        "required": ["name", "steps"],
        "properties": {
            "name": {"type": "string"},
            "router": {
                "type": "string",
                "enum": ["auto", "kernel", "northstar"],
            },
            "variables": {
                "type": "array",
                "items": {"type": "object"},
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "n", "action", "target"],
                    "properties": {
                        "id": {"type": "string"},
                        "n": {"type": "integer"},
                        "action": {"type": "string"},
                        "target": {"type": "object"},
                        "value": {},
                        "executor": {"type": "object"},
                        "screenshot": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "needsReview": {"type": "boolean"},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
    },
}


def compile_to_workflow(
    workflow_id: str,
    frames: list[Path],
    events: list[dict],
    name: str = "Untitled Workflow",
    progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
) -> dict:
    """
    Send selected frames to Claude and receive a structured workflow dict.

    Parameters
    ----------
    workflow_id:
        The workflow ID to embed in the output envelope.
    frames:
        Ordered list of PNG paths to send as vision content.
    events:
        Raw telemetry events (included as metadata in the prompt text).
    name:
        Human-readable workflow name.
    progress_callback:
        Optional async callable(stage, progress, subline).  Called before and
        after the Claude API request.  Runs synchronously via asyncio.run_coroutine_threadsafe
        if a loop is available, otherwise skipped.

    Returns
    -------
    A complete workflow dict ready to serialise to workflow.json.
    """
    client = anthropic.Anthropic()

    _emit_progress(progress_callback, 1, 40, "Identifying UI elements…")

    # Build vision content
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Recording name: {name}\n"
                f"Number of frames: {len(frames)}\n"
                f"Number of telemetry events: {len(events)}"
            ),
        }
    ]
    for i, frame in enumerate(frames):
        b64 = base64.b64encode(frame.read_bytes()).decode()
        content.append({"type": "text", "text": f"Frame {i + 1}:"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            }
        )

    _emit_progress(progress_callback, 2, 70, "Writing agentic script…")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_EMIT_TOOL],
        tool_choice={"type": "tool", "name": "emit_workflow"},
        messages=[{"role": "user", "content": content}],
    )

    _emit_progress(progress_callback, 3, 95, "Optimising execution…")

    # Extract the tool_use block
    for block in response.content:
        if getattr(block, "type", "") == "tool_use" and block.name == "emit_workflow":
            return build_workflow_json(workflow_id, block.input, name)

    raise ValueError("VLM did not call emit_workflow — cannot build workflow JSON")


def build_workflow_json(
    workflow_id: str,
    vlm_output: dict,
    original_name: str = "Untitled",
) -> dict:
    """Merge VLM tool output with the required workflow envelope."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": workflow_id,
        "schemaVersion": 1,
        "name": vlm_output.get("name") or original_name,
        "createdAt": now,
        "updatedAt": now,
        "source": {
            "kind": "recording",
            "videoPath": f"videos/{workflow_id}.mp4",
            "telemetryPath": f"videos/{workflow_id}.events.json",
        },
        "execution": {
            "router": vlm_output.get("router", "auto"),
            "background": True,
            "concurrency": 1,
        },
        "variables": vlm_output.get("variables", []),
        "steps": vlm_output.get("steps", []),
        "outputs": [],
    }


# ── Internal ──────────────────────────────────────────────────────────────────

def _emit_progress(
    cb: Callable | None,
    stage: int,
    progress: int,
    subline: str,
) -> None:
    """Fire the progress callback if one was provided."""
    if cb is None:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(cb(stage, progress, subline))
        else:
            loop.run_until_complete(cb(stage, progress, subline))
    except Exception:
        pass  # Never let a progress notification break compilation
