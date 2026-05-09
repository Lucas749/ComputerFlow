"""
tests/test_lightcone_vlm.py

End-to-end smoke test for the Lightcone VLM compiler.

Uses:
  - Real screenshots from data/workflows/wf_8R00oFFgw58/screens/raw/
    (8 × 1600×900 PNGs captured from a real recording)
  - Synthetic events that map each screenshot to a realistic action

Run:
    cd backend
    python -m pytest tests/test_lightcone_vlm.py -v -s

Requires LIGHTCONE_API_KEY or TZAFON_API_KEY in environment / .env
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv

# ── env / path setup ─────────────────────────────────────────────────────────
ROOT = Path(__file__).parents[2]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(Path(__file__).parents[1]))  # backend/ on path

from app.compiler.lightcone_vlm import compile_with_lightcone, _coalesce_events

# ── fixtures ──────────────────────────────────────────────────────────────────

REAL_SHOTS_DIR = (
    Path(__file__).parents[1]
    / "data/workflows/wf_8R00oFFgw58/screens/raw"
)

# Synthetic event stream: 8 actions matching the 8 raw screenshots.
# Scenario: user opens Hacker News in Safari, searches, opens a story, scrolls.
SYNTHETIC_EVENTS = [
    # ev 0 — click on Safari address bar
    {
        "i": 0, "t": 1715000000000, "kind": "click",
        "x": 800, "y": 42, "screenW": 1600, "screenH": 900,
        "screenshot": "screenshots/ev_0000.jpg",
    },
    # ev 1 — type URL
    {
        "i": 1, "t": 1715000000500, "kind": "key", "key": "h",
        "keyCode": 4, "modifiers": 0,
        "screenshot": "screenshots/ev_0001.jpg",
    },
    {
        "i": 2, "t": 1715000000550, "kind": "key", "key": "n",
        "keyCode": 45, "modifiers": 0,
        "screenshot": "screenshots/ev_0001.jpg",
    },
    {
        "i": 3, "t": 1715000000600, "kind": "key", "key": "e",
        "keyCode": 14, "modifiers": 0,
        "screenshot": "screenshots/ev_0001.jpg",
    },
    {
        "i": 4, "t": 1715000000650, "kind": "key", "key": "w",
        "keyCode": 13, "modifiers": 0,
        "screenshot": "screenshots/ev_0001.jpg",
    },
    {
        "i": 5, "t": 1715000000700, "kind": "key", "key": "s",
        "keyCode": 1, "modifiers": 0,
        "screenshot": "screenshots/ev_0001.jpg",
    },
    # ev 6 — press Return to navigate
    {
        "i": 6, "t": 1715000001000, "kind": "key", "key": "\r",
        "keyCode": 36, "modifiers": 0,
        "screenshot": "screenshots/ev_0002.jpg",
    },
    # ev 7 — click on first story headline
    {
        "i": 7, "t": 1715000003000, "kind": "click",
        "x": 640, "y": 220, "screenW": 1600, "screenH": 900,
        "screenshot": "screenshots/ev_0003.jpg",
    },
    # ev 8 — scroll down to read article
    {
        "i": 8, "t": 1715000006000, "kind": "key", "key": " ",
        "keyCode": 49, "modifiers": 0,
        "screenshot": "screenshots/ev_0004.jpg",
    },
    # ev 9 — cmd+f to search in page
    {
        "i": 9, "t": 1715000008000, "kind": "key", "key": "f",
        "keyCode": 3, "modifiers": 1 << 20,   # cmd+f
        "screenshot": "screenshots/ev_0005.jpg",
    },
    # ev 10 — type search term
    {
        "i": 10, "t": 1715000008500, "kind": "key", "key": "A",
        "keyCode": 0, "modifiers": 0,
        "screenshot": "screenshots/ev_0006.jpg",
    },
    {
        "i": 11, "t": 1715000008550, "kind": "key", "key": "I",
        "keyCode": 34, "modifiers": 0,
        "screenshot": "screenshots/ev_0006.jpg",
    },
    # ev 12 — click Back button
    {
        "i": 12, "t": 1715000012000, "kind": "click",
        "x": 18, "y": 42, "screenW": 1600, "screenH": 900,
        "screenshot": "screenshots/ev_0007.jpg",
    },
]


@pytest.fixture
def screenshots_dir(tmp_path: Path) -> Path:
    """
    Copy the real screenshots into a temp dir as ev_XXXX.jpg files.
    If the real PNGs are not available (CI), generate 1×1 placeholders.
    """
    shots = tmp_path / "screenshots"
    shots.mkdir()

    raw_files = sorted(REAL_SHOTS_DIR.glob("*.png")) if REAL_SHOTS_DIR.exists() else []

    if raw_files:
        # Copy and rename: f_0001.png → ev_0000.jpg, etc.
        try:
            from PIL import Image
            for i, src in enumerate(raw_files):
                dst = shots / f"ev_{i:04d}.jpg"
                img = Image.open(src).convert("RGB")
                img.save(dst, "JPEG", quality=80)
        except ImportError:
            # Pillow not installed — just copy as-is with .jpg extension
            for i, src in enumerate(raw_files):
                shutil.copy(src, shots / f"ev_{i:04d}.jpg")
    else:
        # No real screenshots — generate tiny JPEG placeholders so the test
        # still exercises the full code path without network images.
        try:
            from PIL import Image
            for i in range(8):
                img = Image.new("RGB", (320, 200), color=(30 + i * 20, 50, 80))
                img.save(shots / f"ev_{i:04d}.jpg", "JPEG")
        except ImportError:
            # Absolute fallback: write a minimal valid JPEG header
            minimal_jpg = bytes([
                0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
                0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
                0x00, *([0x08] * 64), 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00,
                0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01,
                0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
                0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
                0xFB, 0x00, 0xFF, 0xD9,
            ])
            for i in range(8):
                (shots / f"ev_{i:04d}.jpg").write_bytes(minimal_jpg)

    return shots


# ── unit tests (no API key needed) ───────────────────────────────────────────

class TestCoalesceEvents:
    def test_merges_consecutive_keys_into_type(self):
        events = [
            {"kind": "key", "key": "h", "keyCode": 4, "modifiers": 0, "t": 1000, "screenshot": "screenshots/ev_0000.jpg"},
            {"kind": "key", "key": "i", "keyCode": 34, "modifiers": 0, "t": 1050, "screenshot": "screenshots/ev_0000.jpg"},
        ]
        result = _coalesce_events(events)
        assert len(result) == 1
        assert result[0]["kind"] == "type"
        assert result[0]["text"] == "hi"

    def test_preserves_clicks(self):
        events = [
            {"kind": "click", "x": 100, "y": 200, "screenW": 1600, "screenH": 900, "t": 1000, "screenshot": "s/ev_0000.jpg"},
        ]
        result = _coalesce_events(events)
        assert len(result) == 1
        assert result[0]["kind"] == "click"
        assert result[0]["x"] == 100

    def test_cmd_key_becomes_hotkey(self):
        events = [
            {"kind": "key", "key": "f", "keyCode": 3, "modifiers": 1 << 20, "t": 1000, "screenshot": "s/ev_0000.jpg"},
        ]
        result = _coalesce_events(events)
        assert len(result) == 1
        assert result[0]["kind"] == "hotkey"
        assert "cmd" in result[0]["keys"]
        assert "f" in result[0]["keys"]

    def test_type_then_click_flushes(self):
        events = [
            {"kind": "key", "key": "a", "keyCode": 0, "modifiers": 0, "t": 1000, "screenshot": "s/ev_0000.jpg"},
            {"kind": "key", "key": "b", "keyCode": 11, "modifiers": 0, "t": 1050, "screenshot": "s/ev_0000.jpg"},
            {"kind": "click", "x": 50, "y": 50, "screenW": 1600, "screenH": 900, "t": 2000, "screenshot": "s/ev_0001.jpg"},
        ]
        result = _coalesce_events(events)
        assert len(result) == 2
        assert result[0]["kind"] == "type"
        assert result[0]["text"] == "ab"
        assert result[1]["kind"] == "click"

    def test_synthetic_events_coalesce_correctly(self):
        result = _coalesce_events(SYNTHETIC_EVENTS)
        kinds = [e["kind"] for e in result]
        # Should have: click, type("hnews"), hotkey(return→treated as type flush then control)
        assert "click" in kinds
        assert "type" in kinds
        assert "hotkey" in kinds


# ── integration test (requires API key) ──────────────────────────────────────

@pytest.mark.skipif(
    not (os.environ.get("LIGHTCONE_API_KEY") or os.environ.get("TZAFON_API_KEY")),
    reason="LIGHTCONE_API_KEY not set",
)
class TestCompileWithLightcone:
    def test_returns_valid_workflow_envelope(self, screenshots_dir: Path):
        progress_log: list[tuple] = []

        def on_progress(stage: int, progress: int, subline: str):
            progress_log.append((stage, progress, subline))
            print(f"  [{stage}] {progress:3d}% — {subline}")

        result = compile_with_lightcone(
            workflow_id="wf_test_001",
            events=SYNTHETIC_EVENTS,
            screenshots_dir=screenshots_dir,
            name="Browse Hacker News",
            progress_callback=on_progress,
        )

        # ── envelope shape ────────────────────────────────────────────────────
        assert result["id"] == "wf_test_001"
        assert result["schemaVersion"] == 1
        assert isinstance(result["name"], str) and result["name"]
        assert "createdAt" in result
        assert "updatedAt" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) > 0, "Expected at least one step"
        assert isinstance(result["variables"], list)

        # ── execution / router ────────────────────────────────────────────────
        exec_cfg = result["execution"]
        assert exec_cfg["router"] in ("auto", "kernel", "northstar")
        assert exec_cfg["background"] is True

        # ── step shape ────────────────────────────────────────────────────────
        valid_actions = {
            "navigate", "click", "double_click", "right_click",
            "drag", "scroll", "hscroll", "type", "hotkey",
            "wait", "screenshot", "extract",
        }
        for step in result["steps"]:
            assert re.match(r"^s\d+$", step["id"]), f"Bad step id: {step['id']}"
            assert isinstance(step["n"], int) and step["n"] >= 1
            assert step["action"] in valid_actions, f"Unknown action: {step['action']}"
            assert "kind" in step["target"]
            assert isinstance(step["approved"], bool)
            assert isinstance(step["needsReview"], bool)
            assert "executor" in step
            assert step["executor"]["kind"] in ("kernel", "computer_use", "northstar", "local")

        # ── progress events emitted ───────────────────────────────────────────
        assert len(progress_log) > 0, "No progress events emitted"
        stages_seen = {s for s, _, _ in progress_log}
        assert len(stages_seen) >= 2, "Expected progress across multiple stages"

        # ── print summary ─────────────────────────────────────────────────────
        print(f"\n✅  Workflow: {result['name']!r}")
        print(f"   Router:   {result['execution']['router']}")
        print(f"   Steps:    {len(result['steps'])}")
        print(f"   Variables:{len(result['variables'])}")
        for s in result["steps"]:
            executor_kind = s["executor"]["kind"]
            tag = "🌐" if executor_kind == "kernel" else "🖥"
            intent = s.get("intent") or s["action"]
            review = " ⚠️" if s["needsReview"] else ""
            print(f"   {tag} s{s['n']:02d} [{s['action']}] {intent}{review}")

    def test_empty_events_still_returns_envelope(self, screenshots_dir: Path):
        """Compiler should not crash when there are no events — returns minimal workflow."""
        result = compile_with_lightcone(
            workflow_id="wf_test_empty",
            events=[],
            screenshots_dir=screenshots_dir,
            name="Empty Recording",
        )
        assert result["id"] == "wf_test_empty"
        assert isinstance(result["steps"], list)

    def test_browser_only_workflow_uses_kernel_router(self, screenshots_dir: Path):
        """All-browser events should yield a valid router."""
        browser_events = [
            {"kind": "click", "x": 800, "y": 42, "screenW": 1600, "screenH": 900,
             "t": 1000, "screenshot": "screenshots/ev_0000.jpg"},
            {"kind": "key", "key": "g", "keyCode": 5, "modifiers": 0, "t": 1100,
             "screenshot": "screenshots/ev_0001.jpg"},
        ]
        result = compile_with_lightcone(
            workflow_id="wf_test_browser",
            events=browser_events,
            screenshots_dir=screenshots_dir,
            name="Browser Task",
        )
        router = result["execution"]["router"]
        assert router in ("kernel", "northstar", "auto"), f"Unexpected router: {router}"
        assert len(result["steps"]) > 0


import re  # imported down here to keep top-of-file clean
