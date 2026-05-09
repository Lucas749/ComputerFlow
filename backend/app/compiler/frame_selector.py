"""
frame_selector.py — Claude-based frame selection.

select_frames():
  Sends candidate frames to Claude claude-sonnet-4-6 in batches of 20 and asks it
  to keep only frames that show a DISTINCT new UI state.
  Returns the subset of Path objects to carry forward to VLM compilation.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import anthropic

from app.compiler.prompts import FRAME_SELECTOR_PROMPT

_BATCH_SIZE = 20


def select_frames(candidates: list[Path]) -> list[Path]:
    """
    Use Claude to pick frames that show a DISTINCT new UI state.

    Processes candidates in batches of 20 to stay within vision context limits.
    Returns the subset of candidate paths to keep (preserves original order).
    """
    if not candidates:
        return []

    client = anthropic.Anthropic()
    kept_paths: list[Path] = []

    for batch_start in range(0, len(candidates), _BATCH_SIZE):
        batch = candidates[batch_start : batch_start + _BATCH_SIZE]
        kept_in_batch = _select_batch(client, batch)
        kept_paths.extend(kept_in_batch)

    return kept_paths


# ── Internal helpers ──────────────────────────────────────────────────────────

def _select_batch(client: anthropic.Anthropic, batch: list[Path]) -> list[Path]:
    """Run one Claude call for a batch of up to 20 frames."""
    content: list[dict] = [
        {"type": "text", "text": f"Images numbered 0 to {len(batch) - 1}:"}
    ]
    for i, p in enumerate(batch):
        b64 = base64.b64encode(p.read_bytes()).decode()
        content.append({"type": "text", "text": f"Image {i}:"})
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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=FRAME_SELECTOR_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        raw_text = "\n".join(
            l for l in lines if not l.startswith("```")
        ).strip()

    try:
        result = json.loads(raw_text)
        indices: list[int] = result.get("keep", [])
    except (json.JSONDecodeError, AttributeError):
        # If parsing fails, keep all frames in the batch
        indices = list(range(len(batch)))

    kept: list[Path] = []
    for idx in indices:
        if isinstance(idx, int) and 0 <= idx < len(batch):
            kept.append(batch[idx])
    return kept
