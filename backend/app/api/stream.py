"""
stream.py — SSE compile-progress endpoint + WebSocket run-log endpoint.

GET  /workflows/{id}/compile/stream   Server-Sent Events
WS   /runs/{id}/stream                WebSocket
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

router = APIRouter()

# ── Compile-progress event bus ────────────────────────────────────────────────
# workflow_id → asyncio.Queue of progress dicts
_compile_queues: dict[str, asyncio.Queue] = {}


def get_compile_queue(workflow_id: str) -> asyncio.Queue:
    """Return (and lazily create) the compile progress queue for a workflow."""
    if workflow_id not in _compile_queues:
        _compile_queues[workflow_id] = asyncio.Queue()
    return _compile_queues[workflow_id]


def drop_compile_queue(workflow_id: str) -> None:
    """Remove the queue (called after SSE client disconnects or compile ends)."""
    _compile_queues.pop(workflow_id, None)


# ── SSE endpoint ──────────────────────────────────────────────────────────────

@router.get("/workflows/{workflow_id}/compile/stream")
async def compile_stream(workflow_id: str):
    """
    Stream compile progress events for a workflow as Server-Sent Events.

    The background compile task posts dicts to the queue via get_compile_queue().
    This endpoint reads from the queue and forwards each event as:

        data: {json}\n\n

    The stream ends when a {"progress": 100} event is received, or after a
    60-second idle timeout.
    """
    queue = get_compile_queue(workflow_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Send a keep-alive comment and stop
                    yield ": keep-alive\n\n"
                    break

                yield f"data: {json.dumps(event)}\n\n"

                # End stream on completion or error
                if event.get("progress") == 100 or event.get("stage") == "error":
                    break
        finally:
            drop_compile_queue(workflow_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── WebSocket run-log endpoint ────────────────────────────────────────────────

@router.websocket("/runs/{run_id}/stream")
async def run_stream(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint that streams run progress events to the client.

    Messages have the shape:
        {"type": str, "line": str, "step": str, "row": dict, "state": str, "ts": float}

    The run_manager posts events to the queue via get_run_queue().
    """
    from app.execution.run_manager import get_run_queue, drop_run_queue

    await websocket.accept()
    queue = get_run_queue(run_id)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
                continue

            try:
                await websocket.send_text(json.dumps(event))
            except Exception:
                break

            # End stream when run is finished
            if event.get("type") == "run_finished":
                break
    except WebSocketDisconnect:
        pass
    finally:
        drop_run_queue(run_id)
        try:
            await websocket.close()
        except Exception:
            pass
