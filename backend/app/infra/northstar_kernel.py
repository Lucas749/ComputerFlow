"""
NorthstarKernelAgent — Kernel browser + Lightcone Northstar CUA loop.

Architecture:
    Kernel  → provides headless cloud browser (AsyncKernel)
    Northstar → Lightcone vision model that decides next action (AsyncLightcone)

Each step:
    1. Capture screenshot from Kernel (PNG bytes → base64)
    2. Send to Northstar Responses API with computer_use tool
    3. Parse computer_call action from response
    4. Execute action on Kernel browser
    5. Repeat until terminate/done/answer or max_steps

Environment variables required:
    KERNEL_API_KEY     — Kernel API key
    TZAFON_API_KEY     — Lightcone / Tzafon API key  (alias: LIGHTCONE_API_KEY)

Usage
-----
    import asyncio
    from app.infra.northstar_kernel import NorthstarKernelAgent

    agent = NorthstarKernelAgent()
    result = await agent.run(
        "Go to news.ycombinator.com and return a summary of the first article"
    )
    print(result.answer)
"""

from __future__ import annotations

import asyncio
import base64
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    answer: str
    steps: int
    events: list[dict] = field(default_factory=list)


class NorthstarKernelAgent:
    """Kernel browser + Northstar Responses API CUA loop (fully async)."""

    TERMINAL_ACTIONS = {"terminate", "done", "answer"}

    def __init__(
        self,
        kernel_api_key: str | None = None,
        lightcone_api_key: str | None = None,
        model: str = "tzafon.northstar-cua-fast",
        viewport_width: int = 1280,
        viewport_height: int = 800,
        step_delay: float = 1.0,
    ) -> None:
        self._kernel_key = (
            kernel_api_key
            or os.environ.get("KERNEL_API_KEY")
            or _required("KERNEL_API_KEY")
        )
        # tzafon reads TZAFON_API_KEY; also accept LIGHTCONE_API_KEY as alias
        self._lightcone_key = (
            lightcone_api_key
            or os.environ.get("TZAFON_API_KEY")
            or os.environ.get("LIGHTCONE_API_KEY")
            or _required("TZAFON_API_KEY")
        )
        self._model = model
        self._vw = viewport_width
        self._vh = viewport_height
        self._step_delay = step_delay

    async def run(
        self,
        task: str,
        max_steps: int = 50,
        stealth: bool = True,
    ) -> AgentResult:
        """Execute task. Returns AgentResult with final answer and step log."""
        from kernel import AsyncKernel
        from tzafon import AsyncLightcone

        kernel = AsyncKernel(api_key=self._kernel_key)
        lc = AsyncLightcone(api_key=self._lightcone_key)
        events: list[dict] = []

        session = await kernel.browsers.create(
            stealth=stealth,
            viewport={"width": self._vw, "height": self._vh},
        )
        sid = session.session_id
        print(f"[kernel] browser {sid} (live: {session.browser_live_view_url})")

        try:
            screenshot_b64 = await _capture(kernel, sid)

            response = await lc.responses.create(
                model=self._model,
                input=[{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": task},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_b64}",
                            "detail": "auto",
                        },
                    ],
                }],
                tools=[_computer_tool(self._vw, self._vh)],
            )
            events.append({"step": 0, "type": "initial_response", "id": response.id})

            for step in range(1, max_steps + 1):
                computer_call = _find_computer_call(response)

                if not computer_call:
                    answer = _extract_text(response)
                    print(f"[northstar] done after {step} steps (no pending action)")
                    return AgentResult(answer=answer, steps=step, events=events)

                action = computer_call.action
                action_type = getattr(action, "type", "unknown")
                print(f"[northstar] step {step}: {action_type}")
                events.append({"step": step, "action": action_type})

                if action_type in self.TERMINAL_ACTIONS:
                    answer = (
                        getattr(action, "text", "")
                        or getattr(action, "answer", "")
                        or _extract_text(response)
                    )
                    return AgentResult(answer=answer, steps=step, events=events)

                await _execute_action(kernel, sid, action)
                await asyncio.sleep(self._step_delay)

                screenshot_b64 = await _capture(kernel, sid)

                response = await lc.responses.create(
                    model=self._model,
                    previous_response_id=response.id,
                    input=[{
                        "type": "computer_call_output",
                        "call_id": computer_call.call_id,
                        "output": {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_b64}",
                            "detail": "auto",
                        },
                    }],
                    tools=[_computer_tool(self._vw, self._vh)],
                )
                events.append({"step": step, "response_id": response.id})

            return AgentResult(
                answer=_extract_text(response),
                steps=max_steps,
                events=events,
            )

        finally:
            try:
                await kernel.browsers.delete_by_id(sid)
                print(f"[kernel] session {sid} deleted")
            except Exception:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _required(var: str) -> str:
    raise ValueError(f"{var} not set in environment")


def _computer_tool(width: int, height: int) -> dict:
    return {
        "type": "computer_use",
        "display_width": width,
        "display_height": height,
        "environment": "browser",
    }


async def _capture(kernel: Any, session_id: str) -> str:
    """Capture screenshot, return base64-encoded PNG string."""
    resp = await kernel.browsers.computer.capture_screenshot(session_id)
    png_bytes = await resp.read()
    return base64.b64encode(png_bytes).decode()


def _find_computer_call(response: Any) -> Any | None:
    for block in getattr(response, "output", []) or []:
        if getattr(block, "type", "") == "computer_call":
            return block
    return None


def _extract_text(response: Any) -> str:
    for block in getattr(response, "output", []) or []:
        block_type = getattr(block, "type", "")

        # Plain text block
        if block_type == "text":
            return getattr(block, "text", "")

        # Message block — content is a list of content objects
        if block_type == "message":
            content = getattr(block, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for c in content:
                    t = getattr(c, "text", None) or getattr(c, "content", None)
                    if t:
                        parts.append(str(t))
                if parts:
                    return "\n".join(parts)

    return ""


async def _execute_action(kernel: Any, session_id: str, action: Any) -> None:
    """Map a Northstar computer_call action to Kernel browser controls."""
    t = getattr(action, "type", "")

    if t == "click":
        await kernel.browsers.computer.click_mouse(session_id, x=action.x, y=action.y)

    elif t == "double_click":
        await kernel.browsers.computer.click_mouse(
            session_id, x=action.x, y=action.y, num_clicks=2
        )

    elif t == "type":
        await kernel.browsers.computer.type_text(session_id, text=action.text)

    elif t in ("key", "keypress"):
        keys = action.keys if isinstance(action.keys, list) else [action.keys]
        await kernel.browsers.computer.press_key(session_id, keys=keys)

    elif t == "scroll":
        await kernel.browsers.computer.scroll(
            session_id,
            x=getattr(action, "x", 640),
            y=getattr(action, "y", 400),
            delta_x=0,
            delta_y=getattr(action, "scroll_y", 0),
        )

    elif t == "drag":
        await kernel.browsers.computer.drag_mouse(
            session_id,
            path=[[action.x, action.y], [action.end_x, action.end_y]],
        )

    elif t == "navigate":
        await kernel.browsers.playwright.execute(
            session_id,
            code=f"await page.goto({getattr(action, 'url', '')!r})",
        )

    elif t == "wait":
        await asyncio.sleep(2)
