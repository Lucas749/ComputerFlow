"""
claude_vlm.py — Compile a recording into workflow.json using Claude Sonnet.

Same chunking strategy as lightcone_vlm.py: max 3 screenshots per call,
multiple sequential calls for longer recordings.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from app.compiler.lightcone_prompts import SYSTEM_PROMPT, CONTINUATION_PROMPT

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_SCREENSHOTS_PER_CALL = 5


# ── Public entry point ────────────────────────────────────────────────────────

def compile_with_claude(
    workflow_id: str,
    events: list[dict],
    screenshots_dir: Path,
    name: str = "Untitled Workflow",
    model: str = DEFAULT_MODEL,
    progress_callback: Optional[Callable[[int, int, str], Any]] = None,
) -> dict:
    """Compile events + screenshots into a workflow.json dict via Claude."""
    from app.compiler.lightcone_vlm import _coalesce_events, _chunk_events, _build_envelope, _resolve_screenshot, _emit

    _emit(progress_callback, 1, 20, "Coalescing events…")
    semantic = _coalesce_events(events)

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

        user_content = _build_claude_content(
            chunk, screenshots_dir,
            step_offset=chunk_start,
            is_continuation=chunk_idx > 0,
            prior_steps=all_steps,
        )

        raw_json = _call_claude(user_content, model, is_continuation=chunk_idx > 0)

        chunk_steps = raw_json.get("steps") or []
        all_steps.extend(chunk_steps)

        if chunk_idx == 0:
            workflow_name = raw_json.get("name") or name
            workflow_summary = (raw_json.get("summary") or "").strip()
            variables = raw_json.get("variables") or []
        else:
            existing_var_names = {v.get("name") for v in variables}
            for v in (raw_json.get("variables") or []):
                if v.get("name") not in existing_var_names:
                    variables.append(v)

    _emit(progress_callback, 2, 85, "Finalising workflow…")
    merged = {"name": workflow_name, "summary": workflow_summary, "steps": all_steps, "variables": variables}
    return _build_envelope(workflow_id, name, merged, semantic)


# ── Build Anthropic message content ──────────────────────────────────────────

def _build_claude_content(
    chunk: list[dict],
    screenshots_dir: Path,
    step_offset: int = 0,
    is_continuation: bool = False,
    prior_steps: list[dict] | None = None,
) -> list[dict]:
    """Build the user message content blocks for the Anthropic Messages API."""
    from app.compiler.lightcone_vlm import _resolve_screenshot

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
            "Produce a complete workflow JSON.\n\nACTIONS:\n"
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
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": b64,
                },
            })

    if is_continuation:
        content.append({"type": "text", "text": "\nReturn ONLY the JSON for these new steps (just {\"steps\": [...]}). Continue numbering from where the prior steps ended:"})
    else:
        content.append({"type": "text", "text": "\nNow return the complete workflow JSON:"})

    return content


# ── Anthropic API call ────────────────────────────────────────────────────────

def _call_claude(user_content: list[dict], model: str, is_continuation: bool = False) -> dict:
    """Call Claude via Anthropic Messages API. Returns parsed workflow dict."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    import anthropic

    client = anthropic.Anthropic(api_key=key)
    system = CONTINUATION_PROMPT if is_continuation else SYSTEM_PROMPT

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        temperature=0.1,
    )

    raw = message.content[0].text if message.content else "{}"
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)
