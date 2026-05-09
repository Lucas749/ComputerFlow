"""
run_manager.py — Orchestrates executing a workflow (or single step).

execute_workflow():
  - Converts the workflow JSON into a FlowRequest
  - Calls ComputerFlowRunner.run_flow()
  - Streams progress to an asyncio.Queue (consumed by the WS endpoint)
  - Updates the Run row in the database throughout

The function is designed to be launched with asyncio.create_task() from the
POST /workflows/{id}/run endpoint.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.infra.runner import ComputerFlowRunner
from app.infra.types import (
    ActionType,
    ExecutionStrategy,
    FlowRequest,
    RunOptions,
    RunTarget,
    SOPStep,
    Surface,
)
from app.store import WorkflowStore, ensure_run_dirs, run_log_path, run_result_path

# Module-level dict: run_id → asyncio.Queue
# The WS endpoint subscribes to this queue.
_run_queues: dict[str, asyncio.Queue] = {}


def get_run_queue(run_id: str) -> asyncio.Queue:
    """Return (and lazily create) the Queue for a given run_id."""
    if run_id not in _run_queues:
        _run_queues[run_id] = asyncio.Queue()
    return _run_queues[run_id]


def drop_run_queue(run_id: str) -> None:
    """Remove the queue after the WS client disconnects."""
    _run_queues.pop(run_id, None)


async def execute_workflow(
    run_id: str,
    workflow_id: str,
    workflow: dict,
    inputs: Optional[list[dict]],
    step_id: Optional[str],
    db: Session,
) -> None:
    """
    Execute a workflow and stream progress events to the run's asyncio.Queue.

    Parameters
    ----------
    run_id:       The Run row ID.
    workflow_id:  The parent Workflow ID (used for file paths).
    workflow:     Parsed workflow.json dict.
    inputs:       List of input variable dicts, e.g. [{"Input": "hello"}].
    step_id:      If set, run only the step with this ID.
    db:           SQLAlchemy session (sync, run in thread executor if needed).
    """
    queue = get_run_queue(run_id)
    store = WorkflowStore(db)
    ensure_run_dirs(workflow_id, run_id)
    log_path = run_log_path(workflow_id, run_id)

    async def emit(event: dict) -> None:
        event.setdefault("ts", time.time())
        await queue.put(event)
        # Append to ndjson log
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
        except Exception:
            pass

    # Mark running
    store.update_run(run_id, status="running")
    await emit({"type": "run_started", "runId": run_id})

    try:
        # Resolve variable substitutions in step values
        merged_inputs: dict[str, Any] = {}
        if inputs:
            for d in inputs:
                merged_inputs.update(d)

        # Build SOPStep list
        steps: list[SOPStep] = []
        for s in workflow.get("steps", []):
            if step_id and s.get("id") != step_id:
                continue

            executor_kind = s.get("executor", {}).get("kind", "kernel")
            surface = Surface.BROWSER if executor_kind == "kernel" else Surface.DESKTOP

            # Resolve variable references in value
            raw_value = s.get("value")
            resolved_value: Optional[str] = None
            if isinstance(raw_value, dict) and raw_value.get("kind") == "var":
                var_name = raw_value.get("ref", "")
                resolved_value = str(merged_inputs.get(var_name, ""))
            elif isinstance(raw_value, str):
                resolved_value = raw_value

            # Resolve target URL/selector
            target_obj = s.get("target", {}) or {}
            target_text: Optional[str] = None
            if target_obj.get("kind") == "url":
                target_text = target_obj.get("value")
            elif target_obj.get("kind") == "selector":
                target_text = resolved_value  # value carries the payload
            description = target_obj.get("description") or target_obj.get("value")

            try:
                action_enum = ActionType(s.get("action", "click"))
            except ValueError:
                action_enum = ActionType.CLICK

            sop = SOPStep(
                intent=f"{s.get('action', 'click')} {description or ''}".strip(),
                action=action_enum,
                surface=surface,
                description=description,
                text=target_text or resolved_value,
            )
            steps.append(sop)

        if not steps:
            raise ValueError("No executable steps found in workflow")

        # Determine execution strategy from workflow router
        router = workflow.get("execution", {}).get("router", "auto")
        strategy_map = {
            "kernel": ExecutionStrategy.CUA_LOOP,
            "northstar": ExecutionStrategy.CUA_LOOP,
            "auto": ExecutionStrategy.CUA_LOOP,
        }
        default_strategy = strategy_map.get(router, ExecutionStrategy.CUA_LOOP)

        target_map = {
            "kernel": RunTarget.KERNEL_BROWSER,
            "northstar": RunTarget.LIGHTCONE_OS,
            "auto": RunTarget.AUTO,
        }
        default_target = target_map.get(router, RunTarget.AUTO)

        summary = (workflow.get("summary") or "").strip()
        goal = summary or f"Execute workflow: {workflow.get('name', '')}"
        flow = FlowRequest(
            title=workflow.get("name", "Untitled"),
            goal=goal,
            steps=steps,
            default_target=default_target,
            default_strategy=default_strategy,
            context=summary,
        )

        runner = ComputerFlowRunner()

        # Runner's on_event is a sync callback invoked from inside async code
        # on the same event loop. Put directly onto the queue (nowait) — this
        # avoids creating cross-thread futures that may never resolve.
        first_live_view_seen = {"v": False}

        def on_event(ev: dict) -> None:
            try:
                ev.setdefault("ts", time.time())
                queue.put_nowait(ev)
                try:
                    with log_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(ev) + "\n")
                except Exception:
                    pass
                if ev.get("type") == "live_view" and not first_live_view_seen["v"]:
                    first_live_view_seen["v"] = True
                    first_url = next(iter((ev.get("urls") or {}).values()), None)
                    if first_url:
                        try:
                            store.update_run(run_id, live_view_url=first_url)
                        except Exception:
                            pass
            except Exception as e:
                print(f"[run_manager] on_event failed: {e}")

        result = await runner.run_flow(flow, on_event=on_event)

        # Fallback: if no live_view event came through, emit from final result
        if result.live_view_urls and not first_live_view_seen["v"]:
            first_url = next(iter(result.live_view_urls.values()), None)
            if first_url:
                store.update_run(run_id, live_view_url=first_url)
            await emit({"type": "live_view", "urls": result.live_view_urls})

        # Persist result to disk
        result_path = run_result_path(workflow_id, run_id)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "answer": result.answer,
                    "stepsTaken": result.steps_taken,
                    "ok": result.ok,
                    "error": result.error,
                    "liveViewUrls": result.live_view_urls,
                    "environmentId": result.environment_id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        final_status = "completed" if result.ok else "error"
        store.finish_run(
            run_id,
            status=final_status,
            output={
                "answer": result.answer,
                "stepsTaken": result.steps_taken,
                "ok": result.ok,
            },
            environment_id=result.environment_id,
        )
        await emit(
            {
                "type": "run_finished",
                "status": final_status,
                "answer": result.answer,
            }
        )

    except Exception as exc:
        store.finish_run(run_id, status="error", output={"error": str(exc)})
        await emit({"type": "run_finished", "status": "error", "error": str(exc)})
        raise
