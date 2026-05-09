"""
lightcone_vlm.py — Compile a recording into workflow.json using Lightcone CUA.

Strategy: send events in chunks of MAX_SCREENSHOTS_PER_CALL. For recordings
with more actions we make multiple sequential calls, each receiving the prior
partial result as context so the model can continue numbering from where it
left off. The partial step lists are merged and wrapped in the standard
envelope.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from app.compiler.lightcone_prompts import SYSTEM_PROMPT, CONTINUATION_PROMPT

DEFAULT_MODEL = "tzafon.northstar-cua-fast-1.6"
MAX_SCREENSHOTS_PER_CALL = 5  # screenshots per Lightcone call


# ── Public entry point ────────────────────────────────────────────────────────

def compile_with_lightcone(
    workflow_id: str,
    events: list[dict],
    screenshots_dir: Path,
    name: str = "Untitled Workflow",
    model: str = DEFAULT_MODEL,
    progress_callback: Optional[Callable[[int, int, str], Any]] = None,
) -> dict:
    """Compile events + screenshots into a workflow.json dict via Lightcone."""
    _emit(progress_callback, 1, 20, "Coalescing events…")
    semantic = _coalesce_events(events)

    # Split into chunks of MAX_SCREENSHOTS_PER_CALL
    chunks = _chunk_events(semantic, MAX_SCREENSHOTS_PER_CALL)
    total_chunks = len(chunks)

    all_steps: list[dict] = []
    workflow_name = name
    workflow_summary = ""
    variables: list[dict] = []

    for chunk_idx, chunk in enumerate(chunks):
        chunk_start = sum(len(c) for c in chunks[:chunk_idx])
        pct_start = 35 + int(chunk_idx / total_chunks * 50)
        _emit(
            progress_callback, 1, pct_start,
            f"Analysing actions {chunk_start + 1}–{chunk_start + len(chunk)}"
            + (f" of {len(semantic)}" if total_chunks > 1 else "") + "…"
        )

        user_content = _build_user_content(
            chunk, screenshots_dir,
            step_offset=chunk_start,
            is_continuation=chunk_idx > 0,
            prior_steps=all_steps,
        )

        raw_json = _call_lightcone(user_content, model, is_continuation=chunk_idx > 0)

        chunk_steps = raw_json.get("steps") or []
        all_steps.extend(chunk_steps)

        if chunk_idx == 0:
            workflow_name = raw_json.get("name") or name
            workflow_summary = (raw_json.get("summary") or "").strip()
            variables = raw_json.get("variables") or []
        else:
            # Merge any new variables from continuation calls
            existing_var_names = {v.get("name") for v in variables}
            for v in (raw_json.get("variables") or []):
                if v.get("name") not in existing_var_names:
                    variables.append(v)

    _emit(progress_callback, 2, 85, "Finalising workflow…")
    merged_llm_output = {"name": workflow_name, "summary": workflow_summary, "steps": all_steps, "variables": variables}
    return _build_envelope(workflow_id, name, merged_llm_output, semantic)


# ── Event coalescing ──────────────────────────────────────────────────────────

def _coalesce_events(events: list[dict]) -> list[dict]:
    """Merge consecutive keystrokes into type steps; keep clicks/hotkeys as-is."""
    out: list[dict] = []
    key_buffer: list[dict] = []

    def flush():
        if not key_buffer:
            return
        text = "".join(e.get("key") or "" for e in key_buffer)
        first = key_buffer[0]
        out.append({
            "kind": "type",
            "t": first.get("t", 0),
            "text": text,
            "screenshot": first.get("screenshot", ""),
        })
        key_buffer.clear()

    for ev in events:
        kind = ev.get("kind", "")
        if kind in ("click", "right_click"):
            flush()
            out.append(ev)
        elif kind == "key":
            key_char = ev.get("key") or ""
            mods = ev.get("modifiers", 0)
            CMD, ALT, CTRL = 1 << 20, 1 << 19, 1 << 18
            if bool(mods & (CMD | ALT | CTRL)) or _is_control(key_char):
                flush()
                keys = _mod_names(mods)
                if key_char:
                    keys.append(key_char)
                out.append({
                    "kind": "hotkey",
                    "t": ev.get("t", 0),
                    "keys": keys,
                    "screenshot": ev.get("screenshot", ""),
                })
            else:
                key_buffer.append(ev)
        elif kind == "keymod":
            key_buffer.append(ev)
        # skip unknown kinds

    flush()
    return out


def _chunk_events(events: list[dict], size: int) -> list[list[dict]]:
    if not events:
        return [[]]
    return [events[i:i + size] for i in range(0, len(events), size)]


def _is_control(s: str) -> bool:
    return bool(s) and (ord(s[0]) < 32 or s in ("\r", "\n", "\t", "\x7f"))


def _mod_names(flags: int) -> list[str]:
    out = []
    if flags & (1 << 20): out.append("cmd")
    if flags & (1 << 19): out.append("alt")
    if flags & (1 << 18): out.append("ctrl")
    if flags & (1 << 17): out.append("shift")
    return out


# ── Build multimodal message content ─────────────────────────────────────────

def _build_user_content(
    chunk: list[dict],
    screenshots_dir: Path,
    step_offset: int = 0,
    is_continuation: bool = False,
    prior_steps: list[dict] | None = None,
) -> list[dict]:
    """
    Build user message content for one chunk of semantic events.
    Each event gets a text description + its screenshot (if available).
    """
    content: list[dict] = []

    if is_continuation and prior_steps:
        prior_summary = json.dumps({"steps": prior_steps[-3:]}, indent=None)
        content.append({"type": "text", "text": (
            f"Continuing workflow analysis. The previous steps ended at step {step_offset}. "
            f"Last completed steps for context:\n{prior_summary}\n\n"
            "Now analyse the NEXT batch of actions below and continue the workflow JSON "
            f"(start at step {step_offset + 1}). Return ONLY the JSON for the new steps.\n\n"
        )})
    else:
        content.append({"type": "text", "text": (
            f"I recorded {step_offset + len(chunk)} user action(s) on macOS. "
            "Below are the actions with their pre-action screenshots. "
            "Produce a complete workflow JSON.\n\n"
            "ACTIONS:\n"
        )})

    for i, ev in enumerate(chunk):
        kind = ev.get("kind", "")
        step_num = step_offset + i + 1

        if kind == "click":
            desc = f"Step {step_num}: CLICK at ({int(ev.get('x', 0))}, {int(ev.get('y', 0))}) on {int(ev.get('screenW', 0))}×{int(ev.get('screenH', 0))} screen"
        elif kind == "right_click":
            desc = f"Step {step_num}: RIGHT-CLICK at ({int(ev.get('x', 0))}, {int(ev.get('y', 0))})"
        elif kind == "type":
            preview = (ev.get("text") or "")[:80].replace("\n", "\\n")
            desc = f'Step {step_num}: TYPE "{preview}"'
        elif kind == "hotkey":
            desc = f"Step {step_num}: HOTKEY {'+'.join(ev.get('keys') or [])}"
        else:
            desc = f"Step {step_num}: {kind.upper()}"

        content.append({"type": "text", "text": desc})

        shot_rel = ev.get("screenshot", "")
        shot_path = _resolve_screenshot(shot_rel, screenshots_dir)
        if shot_path:
            b64 = base64.b64encode(shot_path.read_bytes()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

    if is_continuation:
        content.append({"type": "text", "text": "\nReturn ONLY the JSON for these new steps (no name/variables needed, just {\"steps\": [...]}). Continue numbering from where the prior steps ended:"})
    else:
        content.append({"type": "text", "text": "\nNow return the complete workflow JSON:"})

    return content


# ── Lightcone API call ────────────────────────────────────────────────────────

def _call_lightcone(user_content: list[dict], model: str, is_continuation: bool = False) -> dict:
    """Call Lightcone with retries and a long timeout. Returns parsed workflow dict."""
    key = os.environ.get("LIGHTCONE_API_KEY") or os.environ.get("TZAFON_API_KEY")
    if not key:
        raise RuntimeError("LIGHTCONE_API_KEY not set")

    import tzafon
    import httpx

    client = tzafon.Lightcone(
        api_key=key,
        timeout=httpx.Timeout(connect=15.0, read=180.0, write=60.0, pool=15.0),
        max_retries=3,
    )

    system = CONTINUATION_PROMPT if is_continuation else SYSTEM_PROMPT

    response = client.chat.create_completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=4096,
    )

    if isinstance(response, dict):
        raw = response["choices"][0]["message"]["content"] or "{}"
    else:
        raw = response.choices[0].message.content or "{}"

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)


# ── Envelope assembly ─────────────────────────────────────────────────────────

def _build_envelope(
    workflow_id: str,
    name: str,
    llm_output: dict,
    semantic: list[dict],
) -> dict:
    """Validate LLM output, infer router, and wrap in the full workflow.json envelope."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    final_name = llm_output.get("name") or name
    summary = (llm_output.get("summary") or "").strip()

    raw_steps = llm_output.get("steps") or []
    VALID_ACTIONS = {
        "navigate", "click", "double_click", "right_click",
        "drag", "scroll", "hscroll", "type", "hotkey",
        "wait", "screenshot", "extract",
    }

    steps = []
    for i, step in enumerate(raw_steps):
        executor = step.get("executor") or {}
        if isinstance(executor, str):
            executor = {"kind": executor}
        kind = executor.get("kind", "computer_use")
        if kind not in ("kernel", "computer_use", "northstar", "local"):
            kind = "computer_use"
        entry_fn = "browser_agent.execute_step" if kind == "kernel" else "desktop_agent.execute_step"
        executor = {"kind": kind, "entryFn": entry_fn}

        target = step.get("target") or {}
        if isinstance(target, str):
            target = {"kind": "description", "description": target}
        if "kind" not in target:
            target["kind"] = "description"

        action = step.get("action") or "click"
        if action not in VALID_ACTIONS:
            action = "click"

        value = step.get("value")
        if isinstance(value, dict) and "text" in value and "kind" not in value:
            value = value["text"]

        steps.append({
            "id": step.get("id") or f"s{i+1}",
            "n": step.get("n") or i + 1,
            "action": action,
            "intent": step.get("intent") or "",
            "target": target,
            "value": value,
            "executor": executor,
            "screenshot": step.get("screenshot") or (semantic[i].get("screenshot") if i < len(semantic) else None),
            "approved": False,
            "needsReview": bool(step.get("needsReview", False)),
            "notes": step.get("notes") or "",
        })

    executor_kinds = {s["executor"]["kind"] for s in steps}
    has_browser = "kernel" in executor_kinds
    has_desktop = "computer_use" in executor_kinds or "northstar" in executor_kinds
    if has_browser and has_desktop:
        router = "auto"
    elif has_browser:
        router = "kernel"
    else:
        router = "northstar"

    variables = llm_output.get("variables") or []
    for i, v in enumerate(variables):
        if "id" not in v:
            v["id"] = v.get("name") or f"var{i}"

    return {
        "id": workflow_id,
        "schemaVersion": 1,
        "name": final_name,
        "summary": summary,
        "createdAt": now,
        "updatedAt": now,
        "source": {
            "kind": "recording",
            "videoPath": f"videos/{workflow_id}.mp4",
            "telemetryPath": f"videos/{workflow_id}.events.json",
        },
        "execution": {"router": router, "background": True, "concurrency": 1},
        "variables": variables,
        "steps": steps,
        "outputs": [],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

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
