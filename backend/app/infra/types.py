"""
ComputerFlow action and SOP types.

Shared data contract between:
  - Recorder   → captures raw user actions as RecordedAction objects
  - Compiler   → Claude turns recordings into SOP / SOPStep objects
  - Runner     → executes steps on the right target using the right strategy

Full pipeline
-------------
  list[RecordedAction]
       ↓  (Claude compiler)
  FlowRequest   ← this is what the backend receives from the frontend
       ↓  (ComputerFlowRunner.run_flow)
  FlowResult    ← returned to the frontend with answer + live_view_urls

Target routing
--------------
  RunTarget.KERNEL_BROWSER  →  Kernel cloud browser (Chromium, stealth)
  RunTarget.LIGHTCONE_OS    →  Lightcone cloud desktop (Linux, any app)
  RunTarget.LOCAL           →  User's own machine (macOS/Windows)
  RunTarget.AUTO            →  Runner decides based on step.surface

Strategy routing
----------------
  ExecutionStrategy.AUTONOMOUS  →  Whole task as NL to Northstar Task API
  ExecutionStrategy.CUA_LOOP    →  Manual screenshot → model → action loop
  ExecutionStrategy.DIRECT      →  Replay recorded actions without a model
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Enums ─────────────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    """Every action type that can appear in a step."""
    NAVIGATE     = "navigate"
    CLICK        = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK  = "right_click"
    DRAG         = "drag"
    SCROLL       = "scroll"
    HSCROLL      = "hscroll"
    TYPE         = "type"
    HOTKEY       = "hotkey"
    WAIT         = "wait"
    SCREENSHOT   = "screenshot"   # compiler hint only, not executed


class TargetKind(str, Enum):
    """How the target element is identified within a step."""
    COORDINATE  = "coordinate"   # exact (x, y) pixel position from recording
    SELECTOR    = "selector"     # CSS / XPath selector
    DESCRIPTION = "description"  # natural-language — model resolves visually
    IMAGE       = "image"        # reference screenshot crop — model matches visually


class Surface(str, Enum):
    """Which surface category a step runs on (broad)."""
    BROWSER = "browser"   # web browser
    DESKTOP = "desktop"   # native / OS-level app


class RunTarget(str, Enum):
    """
    Concrete execution target for a step or whole flow.

    AUTO          Runner decides: browser steps → KERNEL_BROWSER,
                  desktop steps  → LIGHTCONE_OS (default cloud) or LOCAL.
    KERNEL_BROWSER Kernel cloud Chromium — stealth, residential proxy.
    LIGHTCONE_OS   Lightcone cloud Linux desktop — any app via apt-get.
    LOCAL          User's own machine — fastest, no cloud cost, needs
                   local CUA agent running.
    """
    AUTO           = "auto"
    KERNEL_BROWSER = "kernel_browser"
    LIGHTCONE_OS   = "lightcone_os"
    LOCAL          = "local"


class ExecutionStrategy(str, Enum):
    """
    How a step or group of steps is executed.

    AUTONOMOUS  One prompt → Northstar Task API drives everything end-to-end.
                Best for: clear, self-contained tasks; quickest to set up.

    CUA_LOOP    Manual screenshot → Northstar → action → repeat.
                Best for: flows where you supply reference screenshots /
                annotations so the model can visually locate elements.
                Follows the CUA protocol (previous_response_id chaining).

    DIRECT      Execute recorded actions directly without calling a model.
                Best for: exact replay of brittle coordinate-based flows;
                fastest; no LLM cost; fails if UI has changed.
    """
    AUTONOMOUS = "autonomous"
    CUA_LOOP   = "cua_loop"
    DIRECT     = "direct"


# ── Raw recorded action (from the recorder) ───────────────────────────────────

@dataclass
class RecordedAction:
    """
    One action captured during a recording session.

    The recorder emits these; the Claude compiler reads them and produces SOPStep.
    """
    type: ActionType
    surface: Surface = Surface.BROWSER
    timestamp_ms: float = 0.0
    screenshot_b64: str | None = None   # full screen at time of action (no data-URI)
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    text: str | None = None             # TYPE text or NAVIGATE url
    keys: list[str] | None = None       # HOTKEY combo
    dx: float = 0.0
    dy: float = 0.0
    url: str | None = None              # current page url
    page_title: str | None = None
    raw: Any = field(default=None, repr=False)


# ── SOP step (compiled) ───────────────────────────────────────────────────────

@dataclass
class SOPStep:
    """
    One step in a compiled Standard Operating Procedure.

    target and strategy can be set per-step to override the flow-level defaults.
    When None, the FlowRequest defaults apply.

    Fields used by the CUA_LOOP executor
    ------------------------------------
    screenshot_b64  Reference screenshot from the recording.  Sent to Northstar
                    alongside the live screenshot so the model can visually match
                    the target element even if layout shifted.
    annotation      Bounding box the UI should overlay on screenshot_b64, e.g.
                    {"x": 120, "y": 340, "w": 80, "h": 30}.
    """
    intent: str                                 # "Click the Export button"
    action: ActionType
    target: RunTarget | None = None             # overrides FlowRequest.default_target
    strategy: ExecutionStrategy | None = None   # overrides FlowRequest.default_strategy
    surface: Surface = Surface.BROWSER
    # Target identification
    target_kind: TargetKind = TargetKind.DESCRIPTION
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    selector: str | None = None
    description: str | None = None
    # Payload
    text: str | None = None                     # TYPE text or NAVIGATE url
    keys: list[str] | None = None               # HOTKEY combo
    dx: float = 0.0
    dy: float = 0.0
    # Visual grounding
    screenshot_b64: str | None = None
    annotation: dict | None = None
    # Timing
    wait_ms: int = 0


# ── Flow request (what the frontend sends) ────────────────────────────────────

@dataclass
class RunOptions:
    """
    Execution options shared across a flow.

    environment_id    Reuse a persistent Lightcone OS environment (saves setup
                      time across runs — e.g. LibreOffice already installed).
    viewport_width    Browser/desktop viewport width in pixels.
    viewport_height   Browser/desktop viewport height in pixels.
    stealth           Enable Kernel bot-detection bypass (residential proxy +
                      fingerprint spoofing).  Only applies to KERNEL_BROWSER.
    step_delay_ms     Milliseconds to wait after each action before capturing
                      the next screenshot.
    max_actions_per_step  Hard cap on CUA loop iterations per SOP step.
    max_total_actions     Hard cap across the whole flow.
    """
    environment_id: str | None = None
    viewport_width: int = 1280
    viewport_height: int = 720
    stealth: bool = True
    step_delay_ms: int = 1000
    max_actions_per_step: int = 15
    max_total_actions: int = 100


@dataclass
class FlowRequest:
    """
    The complete request the frontend sends to run a recorded flow.

    Minimal usage — pure autonomous run on cloud browser:
        FlowRequest(
            title="Export contacts",
            goal="Export all contacts to CSV",
            steps=[...],
        )

    CUA loop on Lightcone OS with reference screenshots:
        FlowRequest(
            title="Fill SAP form",
            goal="...",
            steps=[...],                         # steps have screenshot_b64
            default_target=RunTarget.LIGHTCONE_OS,
            default_strategy=ExecutionStrategy.CUA_LOOP,
        )

    Mixed browser + desktop with handoff:
        FlowRequest(
            title="Scrape then process",
            goal="...",
            steps=[
                SOPStep(..., target=RunTarget.KERNEL_BROWSER),
                SOPStep(..., target=RunTarget.KERNEL_BROWSER),
                SOPStep(..., target=RunTarget.LIGHTCONE_OS),   # handoff
                SOPStep(..., target=RunTarget.LIGHTCONE_OS),
            ],
        )
    """
    title: str
    goal: str
    steps: list[SOPStep]
    default_target: RunTarget = RunTarget.AUTO
    default_strategy: ExecutionStrategy = ExecutionStrategy.CUA_LOOP
    start_url: str | None = None            # browser tasks: navigate here first
    context: str = ""                       # extra context for the model
    options: RunOptions = field(default_factory=RunOptions)

    def to_task_prompt(self) -> str:
        """
        Flatten the flow to a single NL task prompt for AUTONOMOUS strategy.
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
                line += f" → {step.text}"
            elif step.action == ActionType.TYPE and step.text:
                line += f' → type "{step.text}"'
            elif step.action == ActionType.HOTKEY and step.keys:
                line += f" → {'+'.join(step.keys)}"
            parts.append(line)
        return "\n".join(parts)

    def resolved_target(self, step: SOPStep) -> RunTarget:
        """Return the effective target for a step (step overrides flow default)."""
        t = step.target or self.default_target
        if t == RunTarget.AUTO:
            return (
                RunTarget.KERNEL_BROWSER
                if step.surface == Surface.BROWSER
                else RunTarget.LIGHTCONE_OS
            )
        return t

    def resolved_strategy(self, step: SOPStep) -> ExecutionStrategy:
        """Return the effective strategy for a step."""
        return step.strategy or self.default_strategy


# ── Backward-compat aliases (compiler may still produce these) ─────────────────

SOP = FlowRequest
SOPStep = SOPStep
