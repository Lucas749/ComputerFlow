"""
lightcone_vlm.py — Compile a recording into workflow.json using Lightcone's
OpenAI-compatible chat completions API (northstar-cua-fast).

Each pre-action screenshot + action description is sent to the model one at a
time; consecutive keystrokes are coalesced into a single TYPE step first.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from app.compiler.lightcone_prompts import SYSTEM_PROMPT, build_user_prompt

LIGHTCONE_BASE_URL = "https://api.lightcone.ai/v1"
DEFAULT_MODEL = "northstar-cua-fast"


# ── Public entry point ────────────────────────────────────────────────────────

def compile_with_lightcone(
    workflow_id: str,
    events: list[dict],
    screenshots_dir: Path,
    name: str = "Untitled Workflow",
    model: str = DEFAULT_MODEL,
    progress_callback: Optional[Callable[[int, int, str], Any]] = None,
) -> dict:
    """Turn (events + pre-event screenshots) into a workflow.json dict."""
    _emit(progress_callback, 1, 30, "Coalescing events…")
    semantic = coalesce_events(events)

    _emit(progress_callback, 1, 45, f"Describing {len(semantic)} actions…")
    steps: list[dict] = []
    for idx, sem in enumerate(semantic):
        sem.ordinal = idx + 1
        desc = _describe_action(sem, screenshots_dir, model=model)
        steps.append(_to_sop_step(sem, desc))

        pct = 45 + int(40 * (idx + 1) / max(1, len(semantic)))
        _emit(progress_callback, 2, min(pct, 90), f"Step {idx+1}/{len(semantic)}: {desc.intent[:60]}")

    _emit(progress_callback, 3, 95, "Finalising workflow…")
    return _build_envelope(workflow_id, name, _infer_router(steps), [], steps)


# ── Event coalescing ──────────────────────────────────────────────────────────

@dataclass
class SemanticEvent:
    kind: str               # "click" | "right_click" | "type" | "hotkey"
    t_start_ms: float
    t_end_ms: float
    screenshot_rel: str     # path relative to recording root
    x: Optional[float] = None
    y: Optional[float] = None
    screen_w: Optional[float] = None
    screen_h: Optional[float] = None
    text: Optional[str] = None
    keys: Optional[list[str]] = None
    ordinal: int = 0


def coalesce_events(events: list[dict]) -> list[SemanticEvent]:
    out: list[SemanticEvent] = []
    buffer_keys: list[dict] = []

    def flush_keys() -> None:
        if not buffer_keys:
            return
        text = "".join((e.get("key") or "") for e in buffer_keys)
        first = buffer_keys[0]
        out.append(SemanticEvent(
            kind="type",
            t_start_ms=first.get("t", 0),
            t_end_ms=buffer_keys[-1].get("t", 0),
            screenshot_rel=first.get("screenshot", ""),
            text=text,
        ))
        buffer_keys.clear()

    for ev in events:
        kind = ev.get("kind", "")
        if kind in ("click", "right_click"):
            flush_keys()
            out.append(SemanticEvent(
                kind=kind,
                t_start_ms=ev.get("t", 0),
                t_end_ms=ev.get("t", 0),
                screenshot_rel=ev.get("screenshot", ""),
                x=ev.get("x"), y=ev.get("y"),
                screen_w=ev.get("screenW"), screen_h=ev.get("screenH"),
            ))
        elif kind == "key":
            key_char = ev.get("key") or ""
            modifiers = ev.get("modifiers", 0)
            CMD, ALT, CTRL = 1 << 20, 1 << 19, 1 << 18
            has_mod = bool(modifiers & (CMD | ALT | CTRL))
            if has_mod or _is_control_char(key_char):
                flush_keys()
                keys = _mods_to_keys(modifiers)
                if key_char:
                    keys.append(key_char)
                out.append(SemanticEvent(
                    kind="hotkey",
                    t_start_ms=ev.get("t", 0),
                    t_end_ms=ev.get("t", 0),
                    screenshot_rel=ev.get("screenshot", ""),
                    keys=keys,
                ))
            else:
                buffer_keys.append(ev)
        elif kind == "keymod":
            buffer_keys.append({**ev, "_is_mod": True})

    flush_keys()
    return out


def _is_control_char(s: str) -> bool:
    return bool(s) and (ord(s[0]) < 32 or s in ("\r", "\n", "\t", "\x7f"))


def _mods_to_keys(flags: int) -> list[str]:
    keys: list[str] = []
    if flags & (1 << 20): keys.append("cmd")
    if flags & (1 << 19): keys.append("alt")
    if flags & (1 << 18): keys.append("ctrl")
    if flags & (1 << 17): keys.append("shift")
    return keys


# ── Lightcone description ─────────────────────────────────────────────────────

@dataclass
class ActionDescription:
    intent: str
    ui_element: str
    app_context: str
    executor: str       # "kernel" | "computer_use"
    confidence: float


def _describe_action(
    sem: SemanticEvent,
    screenshots_dir: Path,
    model: str = DEFAULT_MODEL,
) -> ActionDescription:
    shot_path = _resolve_screenshot(sem.screenshot_rel, screenshots_dir)

    user_text = build_user_prompt(
        kind=sem.kind,
        x=sem.x, y=sem.y,
        screen_w=sem.screen_w, screen_h=sem.screen_h,
        text=sem.text,
        keys=sem.keys,
    )

    # Build message content — text first, then image if available
    content: list[dict] = [{"type": "text", "text": user_text}]
    if shot_path and shot_path.exists():
        b64 = base64.b64encode(shot_path.read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    try:
        client = _openai_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=512,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return ActionDescription(
            intent=str(data.get("intent", sem.kind)).strip(),
            ui_element=str(data.get("ui_element", "")).strip(),
            app_context=str(data.get("app_context", "")).strip(),
            executor=str(data.get("executor", "computer_use")),
            confidence=float(data.get("confidence", 0.5)),
        )
    except Exception as exc:
        print(f"[CF compiler] Lightcone error on step {sem.ordinal}: {exc}")
        return ActionDescription(
            intent=_fallback_intent(sem),
            ui_element="",
            app_context="",
            executor="computer_use",
            confidence=0.0,
        )


def _fallback_intent(sem: SemanticEvent) -> str:
    if sem.kind == "click":
        return f"Click at ({int(sem.x or 0)}, {int(sem.y or 0)})"
    if sem.kind == "right_click":
        return f"Right-click at ({int(sem.x or 0)}, {int(sem.y or 0)})"
    if sem.kind == "type":
        return f'Type "{(sem.text or "")[:40]}"'
    if sem.kind == "hotkey":
        return f"Press {'+'.join(sem.keys or [])}"
    return sem.kind


# ── SOP step assembly ─────────────────────────────────────────────────────────

def _to_sop_step(sem: SemanticEvent, desc: ActionDescription) -> dict:
    step_id = f"s{sem.ordinal}"
    executor_kind = desc.executor if desc.executor in ("kernel", "computer_use") else "computer_use"
    base = {
        "id": step_id,
        "n": sem.ordinal,
        "intent": desc.intent,
        "notes": desc.ui_element,
        "app_context": desc.app_context,
        "screenshot": sem.screenshot_rel,
        "approved": False,
        "needsReview": desc.confidence < 0.6,
    }

    executor_obj: dict = {
        "kind": executor_kind,
        "entryFn": "browser_agent.execute_step" if executor_kind == "kernel" else "desktop_agent.execute_step",
    }

    if sem.kind == "click":
        return {
            **base,
            "action": "click",
            "target": {
                "kind": "description",
                "description": desc.ui_element or desc.intent,
                "x": sem.x, "y": sem.y,
                "screenW": sem.screen_w, "screenH": sem.screen_h,
            },
            "value": None,
            "executor": executor_obj,
        }
    if sem.kind == "right_click":
        return {
            **base,
            "action": "right_click",
            "target": {
                "kind": "description",
                "description": desc.ui_element or desc.intent,
                "x": sem.x, "y": sem.y,
            },
            "value": None,
            "executor": executor_obj,
        }
    if sem.kind == "type":
        return {
            **base,
            "action": "type",
            "target": {"kind": "description", "description": desc.ui_element or desc.intent},
            "value": {"kind": "literal", "text": sem.text or ""},
            "executor": executor_obj,
        }
    if sem.kind == "hotkey":
        return {
            **base,
            "action": "hotkey",
            "target": {"kind": "none"},
            "value": {"kind": "keys", "keys": sem.keys or []},
            "executor": executor_obj,
        }
    return {**base, "action": sem.kind, "target": {"kind": "none"}, "value": None}


def _build_envelope(
    workflow_id: str,
    name: str,
    router: str,
    variables: list[dict],
    steps: list[dict],
) -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": workflow_id,
        "schemaVersion": 1,
        "name": name,
        "createdAt": now,
        "updatedAt": now,
        "source": {
            "kind": "recording",
            "videoPath": f"videos/{workflow_id}.mp4",
            "telemetryPath": f"videos/{workflow_id}.events.json",
            "eventScreenshotsDir": "screens/events",
        },
        "execution": {"router": router, "background": True, "concurrency": 1},
        "variables": variables,
        "steps": steps,
        "outputs": [],
    }


def _infer_router(steps: list[dict]) -> str:
    # Default to auto; runner resolves per-step based on executor.kind
    return "auto"


# ── OpenAI-compatible client pointed at Lightcone ────────────────────────────

_client_singleton: Any = None


def _openai_client() -> Any:
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    key = os.environ.get("LIGHTCONE_API_KEY") or os.environ.get("TZAFON_API_KEY")
    if not key:
        raise RuntimeError("LIGHTCONE_API_KEY not set")
    from openai import OpenAI
    _client_singleton = OpenAI(api_key=key, base_url=LIGHTCONE_BASE_URL)
    return _client_singleton


def _resolve_screenshot(rel: str, screenshots_dir: Path) -> Optional[Path]:
    if not rel:
        return None
    name = Path(rel).name
    candidate = screenshots_dir / name
    return candidate if candidate.exists() else None


def _emit(cb: Optional[Callable], stage: int, progress: int, subline: str) -> None:
    if cb is None:
        return
    try:
        import asyncio
        res = cb(stage, progress, subline)
        if asyncio.iscoroutine(res):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(res, loop)
            except Exception:
                pass
    except Exception:
        pass
