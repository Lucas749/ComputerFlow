"""
lightcone_vlm.py — compile a recording into workflow.json using Lightcone's
multimodal chat completion API (tzafon.northstar-cua-fast).

Why Lightcone CUA instead of the video-based Claude pipeline?
  - The Mac client now captures a lossless screenshot BEFORE every click /
    keystroke.  These are pixel-perfect and timed to the event — no need to
    re-derive key frames from a compressed video.
  - The Lightcone CUA model is the same model that *executes* workflows, so
    asking it to describe what happened tends to produce descriptions it can
    later re-ground.

Input:
  events: list[dict]         ← from events.json produced by EventTelemetry
    each has:
      { "i": int, "t": ms, "kind": "click"|"right_click"|"key"|"keymod",
        "x": px, "y": px,           (clicks)
        "key": "a", "keyCode": 0, "modifiers": int,   (keys)
        "screenshot": "screenshots/ev_0000.jpg",
        "screenW": px, "screenH": px }
  screenshots_dir: Path      ← disk folder holding ev_XXXX.jpg

Output:
  dict matching the workflow.schema.json envelope, with one SOPStep per
  semantic user action (keystrokes are coalesced into TYPE steps).
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from app.compiler.prompts import LIGHTCONE_SYSTEM_PROMPT

# Model note: Lightcone's CUA-fast model is vision-capable and cheap enough
# for compile-time usage.  For tougher recordings bump to `tzafon.northstar-cua`.
DEFAULT_MODEL = "tzafon.northstar-cua-fast"


# ── Public entry point ────────────────────────────────────────────────────────

def compile_with_lightcone(
    workflow_id: str,
    events: list[dict],
    screenshots_dir: Path,
    name: str = "Untitled Workflow",
    model: str = DEFAULT_MODEL,
    progress_callback: Optional[Callable[[int, int, str], Any]] = None,
) -> dict:
    """
    Turn (events + pre-event screenshots) into a workflow.json dict.

    1. Coalesce consecutive key events into TYPE steps (humans type 5 keys for
       one semantic "type 'hello'" action).
    2. For each semantic step, ask Lightcone to describe what the user did,
       given the screenshot that was captured BEFORE the action.
    3. Combine descriptions + low-level coordinates into SOPSteps.
    """
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
    router = _infer_router(steps)
    variables = _extract_variables(steps)

    return _build_envelope(workflow_id, name, router, variables, steps)


# ── Event coalescing ──────────────────────────────────────────────────────────

@dataclass
class SemanticEvent:
    """One human-meaningful action."""
    kind: str                    # "click" | "right_click" | "type" | "hotkey"
    t_start_ms: float
    t_end_ms: float
    screenshot_rel: str          # path relative to recording root
    # Click-like
    x: Optional[float] = None
    y: Optional[float] = None
    screen_w: Optional[float] = None
    screen_h: Optional[float] = None
    # Text
    text: Optional[str] = None
    # Hotkey
    keys: Optional[list[str]] = None
    ordinal: int = 0             # filled by compile_with_lightcone


def coalesce_events(events: list[dict]) -> list[SemanticEvent]:
    """
    Merge runs of keypresses into a single "type" action, preserve clicks and
    right-clicks as-is, and turn modifier-chord keydowns into "hotkey" actions.
    """
    out: list[SemanticEvent] = []
    buffer_keys: list[dict] = []     # consecutive simple keystrokes

    def flush_keys() -> None:
        if not buffer_keys:
            return
        text = "".join((e.get("key") or "") for e in buffer_keys)
        # Keep the very first screenshot — that's the state BEFORE the user
        # started typing.
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
        if kind == "click" or kind == "right_click":
            flush_keys()
            out.append(SemanticEvent(
                kind=kind,
                t_start_ms=ev.get("t", 0),
                t_end_ms=ev.get("t", 0),
                screenshot_rel=ev.get("screenshot", ""),
                x=ev.get("x"), y=ev.get("y"),
                screen_w=ev.get("screenW"), screen_h=ev.get("screenH"),
            ))
        elif kind == "keymod":
            # A pure modifier press → fold into the next key as a hotkey.
            # Simpler heuristic: if the very next event is a keydown within
            # 500 ms, emit a hotkey; otherwise drop it.
            flush_keys()
            # Treat as standalone modifier marker; combined below if next is key
            buffer_keys.append({**ev, "_is_mod": True})
        elif kind == "key":
            key_char = ev.get("key") or ""
            modifiers = ev.get("modifiers", 0)
            # Modifier-held key → hotkey (⌘, ⌥, ⌃, ⇧ roughly = bits 20,19,18,17)
            CMD, ALT, CTRL, SHIFT = 1 << 20, 1 << 19, 1 << 18, 1 << 17
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
        else:
            # Unknown kind — skip
            continue

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


# ── Lightcone CUA description ─────────────────────────────────────────────────

@dataclass
class ActionDescription:
    intent: str                  # "Click the blue Submit button"
    ui_element: str              # "Submit button in the footer of a signup form"
    app_context: str             # "Browser on https://example.com"
    confidence: float            # 0..1


def _describe_action(
    sem: SemanticEvent,
    screenshots_dir: Path,
    model: str = DEFAULT_MODEL,
) -> ActionDescription:
    """Ask Lightcone to describe one action, given the pre-action screenshot."""
    shot_path = _resolve_screenshot(sem.screenshot_rel, screenshots_dir)
    img_b64 = _b64_image(shot_path) if shot_path else None

    prompt = _build_description_prompt(sem)

    client = _lightcone_client()
    content: list[dict] = [{"type": "text", "text": prompt}]
    if img_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
        })

    try:
        response = client.chat.create_completion(
            model=model,
            messages=[
                {"role": "system", "content": LIGHTCONE_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=512,
        )
        text = _extract_text(response)
        data = json.loads(text)
        return ActionDescription(
            intent=str(data.get("intent", sem.kind)).strip(),
            ui_element=str(data.get("ui_element", "")).strip(),
            app_context=str(data.get("app_context", "")).strip(),
            confidence=float(data.get("confidence", 0.5)),
        )
    except Exception as exc:
        # Fallback: synthesise a plain description so compilation still succeeds.
        return ActionDescription(
            intent=_fallback_intent(sem),
            ui_element="",
            app_context="",
            confidence=0.0,
        )


def _build_description_prompt(sem: SemanticEvent) -> str:
    if sem.kind == "click":
        return (
            f"The user clicked at screen coordinates ({int(sem.x or 0)}, {int(sem.y or 0)}) "
            f"on a {int(sem.screen_w or 0)}×{int(sem.screen_h or 0)} screen. "
            "Look at the screenshot (which was captured IMMEDIATELY BEFORE the click) and describe "
            "what the user intended to do."
        )
    if sem.kind == "right_click":
        return (
            f"The user right-clicked at ({int(sem.x or 0)}, {int(sem.y or 0)}). "
            "Describe what context menu the user was trying to open."
        )
    if sem.kind == "type":
        preview = (sem.text or "").replace("\n", "\\n")[:80]
        return (
            f'The user typed: "{preview}". '
            "From the pre-typing screenshot, describe which field they focused "
            "and what they were entering."
        )
    if sem.kind == "hotkey":
        combo = "+".join(sem.keys or [])
        return (
            f"The user pressed the hotkey {combo}. "
            "From the pre-press screenshot, describe the app state and what "
            "this shortcut is likely doing."
        )
    return "Describe the user action shown in the screenshot."


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
    base = {
        "id": step_id,
        "n": sem.ordinal,
        "notes": desc.ui_element,
        "screenshot": sem.screenshot_rel,  # frontend already has this path
        "approved": False,
        "needsReview": desc.confidence < 0.6,
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
            "executor": {
                "kind": "computer_use",
                "entryFn": "desktop_agent.execute_step",
                "strategy": "computer_use_primary",
                "coordinateFallback": "northstar",
                "confidenceThreshold": 0.6,
            },
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
            "executor": {"kind": "computer_use", "entryFn": "desktop_agent.execute_step"},
        }
    if sem.kind == "type":
        return {
            **base,
            "action": "type",
            "target": {"kind": "description", "description": desc.ui_element or desc.intent},
            "value": {"kind": "literal", "text": sem.text or ""},
            "executor": {"kind": "computer_use", "entryFn": "desktop_agent.execute_step"},
        }
    if sem.kind == "hotkey":
        return {
            **base,
            "action": "hotkey",
            "target": {"kind": "none"},
            "value": {"kind": "keys", "keys": sem.keys or []},
            "executor": {"kind": "computer_use", "entryFn": "desktop_agent.execute_step"},
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
    # Heuristic: if every step target description hints at a browser URL, use kernel.
    # For now default to auto — the runner resolves per-step.
    return "auto"


def _extract_variables(steps: list[dict]) -> list[dict]:
    # First pass: no auto-variable lifting.  The Editor lets the user promote
    # a literal value into a variable manually.  We keep this function so the
    # envelope shape stays stable.
    return []


# ── Low-level helpers ─────────────────────────────────────────────────────────

_client_singleton: Any = None


def _lightcone_client() -> Any:
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    key = os.environ.get("TZAFON_API_KEY") or os.environ.get("LIGHTCONE_API_KEY")
    if not key:
        raise RuntimeError("TZAFON_API_KEY / LIGHTCONE_API_KEY not set")
    from tzafon import Lightcone   # sync client (we call from a worker thread)
    _client_singleton = Lightcone(api_key=key)
    return _client_singleton


def _resolve_screenshot(rel: str, screenshots_dir: Path) -> Optional[Path]:
    """
    events.json stores paths like "screenshots/ev_0000.jpg".
    The Mac client uploaded each JPEG flat into `data/workflows/{id}/screens/events/`,
    so we strip any leading folder.
    """
    if not rel:
        return None
    name = Path(rel).name
    candidate = screenshots_dir / name
    return candidate if candidate.exists() else None


def _b64_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _extract_text(response: Any) -> str:
    """
    The chat/completions response format is OpenAI-compatible:
        response.choices[0].message.content
    Fall back to other attribute shapes just in case the SDK evolves.
    """
    choices = getattr(response, "choices", None)
    if choices:
        first = choices[0]
        msg = getattr(first, "message", None)
        if msg is not None:
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
    # Dict-style fallback
    if isinstance(response, dict):
        try:
            return response["choices"][0]["message"]["content"]
        except Exception:
            pass
    return "{}"


def _emit(
    cb: Optional[Callable],
    stage: int,
    progress: int,
    subline: str,
) -> None:
    if cb is None:
        return
    try:
        import asyncio
        res = cb(stage, progress, subline)
        if asyncio.iscoroutine(res):
            # Scheduled on whatever loop is running; we're in executor so punt.
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(res, loop)
            except Exception:
                pass
    except Exception:
        pass
