"""
frames.py — AI-selected candidate frame extraction from a video.

extract_candidates():
  1. Extracts frames at 2 fps via ffmpeg.
  2. Optionally inserts extra frames ±150 ms around each click event.
  Returns a sorted list of PNG Paths in <video_dir>/raw/.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_candidates(
    video_path: Path,
    events: list[dict] | None = None,
) -> list[Path]:
    """
    Extract candidate frames from a video file.

    Parameters
    ----------
    video_path:
        Path to the source .mp4 file.
    events:
        Optional list of telemetry event dicts.  Any event with
        ``type`` in ("click", "mousedown", "keydown") triggers an extra
        frame extraction ±150 ms around that timestamp.

    Returns
    -------
    Sorted list of PNG file paths in ``<video_parent>/raw/``.
    """
    out_dir = video_path.parent.parent / "screens" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- 2 fps baseline extraction ------------------------------------------
    # Use subprocess so we don't need the ffmpeg binary on PATH for the import;
    # fall back to ffmpeg-python if available.
    _extract_fps(video_path, out_dir, fps=2)

    # -- Extra frames around click/key events --------------------------------
    if events:
        click_times_s = _collect_click_times(events)
        for ts in click_times_s:
            _extract_single_frame(video_path, out_dir, ts)

    return sorted(out_dir.glob("*.png"))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_fps(video_path: Path, out_dir: Path, fps: int = 2) -> None:
    """Extract frames at `fps` frames per second via ffmpeg subprocess."""
    try:
        import ffmpeg  # type: ignore

        (
            ffmpeg
            .input(str(video_path))
            .filter("fps", fps=fps)
            .output(str(out_dir / "f_%04d.png"))
            .overwrite_output()
            .run(quiet=True)
        )
    except ImportError:
        # Fall back to bare subprocess
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"fps={fps}",
            str(out_dir / "f_%04d.png"),
        ]
        subprocess.run(cmd, check=True, capture_output=True)


def _extract_single_frame(video_path: Path, out_dir: Path, ts_s: float) -> None:
    """Extract a single frame at timestamp `ts_s` seconds."""
    # Use a unique name based on the timestamp (milliseconds, zero-padded)
    name = f"ev_{int(ts_s * 1000):08d}.png"
    out_file = out_dir / name
    if out_file.exists():
        return

    try:
        import ffmpeg  # type: ignore

        (
            ffmpeg
            .input(str(video_path), ss=ts_s)
            .output(str(out_file), vframes=1)
            .overwrite_output()
            .run(quiet=True)
        )
    except ImportError:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(ts_s),
            "-i", str(video_path),
            "-vframes", "1",
            str(out_file),
        ]
        subprocess.run(cmd, check=False, capture_output=True)


def _collect_click_times(events: list[dict]) -> list[float]:
    """
    Return unique timestamps (seconds) for click/key events, deduplicated
    within a 150 ms window to avoid extracting many redundant frames.
    """
    CLICK_TYPES = {"click", "mousedown", "dblclick", "keydown"}
    WINDOW_MS = 150

    raw: list[float] = []
    for ev in events:
        if ev.get("type") in CLICK_TYPES:
            ts = ev.get("timestamp") or ev.get("ts") or ev.get("time")
            if ts is not None:
                raw.append(float(ts) / 1000.0)  # assume timestamps are in ms

    if not raw:
        return []

    raw.sort()
    deduped: list[float] = [raw[0]]
    for t in raw[1:]:
        if (t - deduped[-1]) * 1000 >= WINDOW_MS:
            deduped.append(t)
    return deduped
