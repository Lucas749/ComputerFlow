"""
ComputerFlow action and SOP types.

These are the shared data contracts between:
  - The recorder  (captures raw user actions)
  - The compiler  (Claude turns recordings into SOP steps)
  - The runner    (executes SOP steps using the right infra)

Flow
----
  User records → list[RecordedAction]
        ↓  (Claude compiler)
  SOP (list[SOPStep] + metadata)
        ↓  (ComputerFlowRunner.execute_sop)
  RunResult

The compiler chooses the right ExecutionMode for each SOP based on the
action types and target surface (browser vs desktop app).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Enums ─────────────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    """Every action that can appear in a recorded flow or SOP step."""
    # Navigation
    NAVIGATE     = "navigate"      # Go to URL
    # Mouse
    CLICK        = "click"         # Single left click
    DOUBLE_CLICK = "double_click"  # Double click
    RIGHT_CLICK  = "right_click"   # Right / context-menu click
    DRAG         = "drag"          # Drag from one point to another
    SCROLL       = "scroll"        # Scroll wheel
    # Keyboard
    TYPE         = "type"          # Type a string
    HOTKEY       = "hotkey"        # Key combo, e.g. ["ctrl", "c"]
    # Page / window
    WAIT         = "wait"          # Pause execution
    SCREENSHOT   = "screenshot"    # Capture state (compiler hint, not executed)


class TargetKind(str, Enum):
    """How the target element is identified."""
    COORDINATE  = "coordinate"   # Raw (x, y) pixel position
    SELECTOR    = "selector"     # CSS / XPath selector
    DESCRIPTION = "description"  # Natural-language description (model resolves it)
    IMAGE       = "image"        # Crop of the reference screenshot (visual match)


class Surface(str, Enum):
    """Which surface the SOP runs on."""
    BROWSER = "browser"   # Web browser — use BROWSER_CUA or BROWSER_TASK
    DESKTOP = "desktop"   # Desktop / native apps — use DESKTOP_TASK


# ── Recorded action (raw capture) ─────────────────────────────────────────────

@dataclass
class RecordedAction:
    """
    One action captured during a user recording session.

    The recorder emits these; the compiler reads them and produces SOPStep objects.

    Fields
    ------
    type            What kind of action this is.
    surface         Was this on the browser or the desktop?
    timestamp_ms    Wall-clock ms since recording started.
    screenshot_b64  Full-screen PNG at the moment of the action (no data-URI prefix).
    x, y            Pixel coordinates (click / scroll / drag start).
    end_x, end_y    Drag endpoint.
    text            Text typed or URL navigated to.
    keys            Key combo for HOTKEY actions, e.g. ["ctrl", "s"].
    dx, dy          Scroll deltas.
    url             Current page URL (browser surface only).
    page_title      Current page title (browser surface only).
    raw             Original event from the OS capture layer.
    """
    type: ActionType
    surface: Surface = Surface.BROWSER
    timestamp_ms: float = 0.0
    screenshot_b64: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    text: str | None = None
    keys: list[str] | None = None
    dx: float = 0.0
    dy: float = 0.0
    url: str | None = None
    page_title: str | None = None
    raw: Any = field(default=None, repr=False)


# ── SOP step (compiled) ───────────────────────────────────────────────────────

@dataclass
class SOPStep:
    """
    One step in a Standard Operating Procedure, compiled from recorded actions.

    The model that replays the SOP uses these fields to decide what call to make
    and how to locate the target element.

    Fields
    ------
    intent          Human-readable goal, e.g. "Click the Login button".
                    Also used as the instruction when sending to Northstar.
    action          The action to perform.
    target_kind     How the target is identified (coordinate / selector / etc.).
    x, y            Pixel coords when target_kind=COORDINATE.
    end_x, end_y    Drag endpoint (DRAG action only).
    selector        CSS / XPath selector when target_kind=SELECTOR.
    description     NL description when target_kind=DESCRIPTION.
                    Northstar resolves this visually.
    text            String to type (TYPE) or URL to navigate to (NAVIGATE).
    keys            Key combo for HOTKEY, e.g. ["ctrl", "s"].
    dy              Scroll amount (positive = down, negative = up).
    screenshot_b64  Reference screenshot from the recording (no data-URI prefix).
                    Used for visual grounding when target_kind=IMAGE or DESCRIPTION.
    annotation      Optional bounding box / highlight dict, e.g.
                    {"x": 100, "y": 200, "w": 80, "h": 30}.
                    The UI can overlay this on the reference screenshot.
    wait_ms         Optional pause after this step completes (ms).
    """
    intent: str
    action: ActionType
    target_kind: TargetKind = TargetKind.DESCRIPTION
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    selector: str | None = None
    description: str | None = None
    text: str | None = None
    keys: list[str] | None = None
    dy: float = 0.0
    screenshot_b64: str | None = None
    annotation: dict | None = None
    wait_ms: int = 0


# ── SOP (full plan) ───────────────────────────────────────────────────────────

@dataclass
class SOP:
    """
    A complete Standard Operating Procedure ready for the runner.

    Produced by the compiler (Claude); consumed by ComputerFlowRunner.execute_sop().

    Fields
    ------
    title           Short name for this procedure.
    goal            One-sentence description of what completing this SOP achieves.
    surface         Browser or desktop — determines which executor to use.
    steps           Ordered list of steps to execute.
    start_url       For browser tasks: navigate here before step 1.
    environment_id  Reuse a persistent Lightcone environment (leave None for fresh).
    context         Any additional context the agent should know (credentials hint,
                    domain-specific info, etc.).
    """
    title: str
    goal: str
    surface: Surface
    steps: list[SOPStep]
    start_url: str | None = None
    environment_id: str | None = None
    context: str = ""

    def to_task_prompt(self) -> str:
        """
        Flatten the SOP into a single natural-language task prompt.

        Used when the executor mode is DESKTOP_TASK or BROWSER_TASK (fully
        autonomous) — Northstar receives the whole plan as one instruction.
        """
        parts: list[str] = []

        if self.context:
            parts.append(self.context.strip())

        if self.start_url:
            parts.append(f"Start at: {self.start_url}")

        parts.append(f"Goal: {self.goal}")
        parts.append("\nSteps:")
        for i, step in enumerate(self.steps, 1):
            line = f"  {i}. {step.intent}"
            if step.action == ActionType.NAVIGATE and step.text:
                line += f" → navigate to {step.text}"
            elif step.action == ActionType.TYPE and step.text:
                line += f' → type "{step.text}"'
            elif step.action == ActionType.HOTKEY and step.keys:
                line += f" → press {'+'.join(step.keys)}"
            parts.append(line)

        return "\n".join(parts)

    def to_step_prompts(self) -> list[str]:
        """
        Convert each step to a standalone instruction string.

        Used when executing step-by-step with visual guidance (each step
        gets its own Northstar call alongside the reference screenshot).
        """
        prompts = []
        for step in self.steps:
            p = step.intent
            if step.action == ActionType.TYPE and step.text:
                p += f' Type: "{step.text}"'
            elif step.action == ActionType.NAVIGATE and step.text:
                p += f" Navigate to: {step.text}"
            elif step.action == ActionType.HOTKEY and step.keys:
                p += f" Press: {'+'.join(step.keys)}"
            elif step.description:
                p += f" Target: {step.description}"
            prompts.append(p)
        return prompts
