"""
ComputerFlowRunner — single entry point for all task execution.

The runner takes a FlowRequest (list of typed SOP steps) and routes each
step to the right backend. It handles:

  1. KERNEL_BROWSER  — Kernel cloud Chromium + Northstar CUA loop
  2. LIGHTCONE_OS    — Lightcone cloud Linux desktop + Northstar CUA loop
  3. LOCAL           — User's own machine + Northstar CUA loop (local capture)

  4. AUTONOMOUS strategy  — whole task as one NL prompt → Northstar Task API
  5. CUA_LOOP strategy    — manual screenshot → model → action loop (CUA protocol)
  6. DIRECT strategy      — replay recorded coordinates directly, no model

  7. Mixed / handoff      — consecutive steps with different targets trigger a
                            session handoff automatically.

Primary call
------------
    runner = ComputerFlowRunner()
    result = await runner.run_flow(flow_request)
    print(result.answer)
    print(result.live_view_urls)   # {"kernel_browser": "...", "lightcone_os": "..."}
"""

from __future__ import annotations

import asyncio
import base64
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from app.infra.types import (
    ActionType,
    ExecutionStrategy,
    FlowRequest,
    RunOptions,
    RunTarget,
    SOPStep,
    Surface,
)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class FlowResult:
    """
    Outcome of a full flow execution.

    live_view_urls    Map of target → live-view URL so the frontend can show
                      the user what's happening on each surface in real time.
                      Keys match RunTarget values, e.g. "kernel_browser".
    environment_id    If a persistent Lightcone OS environment was used or
                      created, save this and pass it back next time to skip
                      environment setup.
    """
    answer: str
    steps_taken: int
    live_view_urls: dict[str, str] = field(default_factory=dict)
    environment_id: str | None = None
    replay_id: str | None = None      # Kernel session replay ID (browser flows)
    events: list[Any] = field(default_factory=list)
    ok: bool = True
    error: str | None = None


# ── CUA backend protocol ──────────────────────────────────────────────────────

@runtime_checkable
class CUABackend(Protocol):
    """
    Interface all three CUA backends must implement.

    The CUA loop in _run_cua_loop() calls only these two methods, so swapping
    KERNEL_BROWSER / LIGHTCONE_OS / LOCAL is a matter of passing a different backend.
    """
    async def screenshot_b64(self) -> str:
        """Capture current screen, return bare base64-encoded PNG."""
        ...

    async def execute_action(self, action: Any) -> None:
        """Execute one Northstar computer_call action on the target surface."""
        ...


# ── Kernel browser backend ────────────────────────────────────────────────────

class KernelBrowserBackend:
    """CUA backend that controls a Kernel cloud Chromium session."""

    def __init__(self, kernel_sdk: Any, session_id: str) -> None:
        self._k = kernel_sdk
        self._sid = session_id

    async def screenshot_b64(self) -> str:
        resp = await self._k.browsers.computer.capture_screenshot(self._sid)
        return base64.b64encode(await resp.read()).decode()

    async def execute_action(self, action: Any) -> None:
        t = getattr(action, "type", "")

        if t == "click":
            await self._k.browsers.computer.click_mouse(self._sid, x=action.x, y=action.y)

        elif t == "double_click":
            await self._k.browsers.computer.click_mouse(
                self._sid, x=action.x, y=action.y, num_clicks=2
            )

        elif t == "right_click":
            await self._k.browsers.computer.click_mouse(
                self._sid, x=action.x, y=action.y, button="right"
            )

        elif t == "type":
            await self._k.browsers.computer.type_text(self._sid, text=action.text)

        elif t in ("key", "keypress"):
            keys = action.keys if isinstance(action.keys, list) else [action.keys]
            await self._k.browsers.computer.press_key(self._sid, keys=keys)

        elif t == "scroll":
            await self._k.browsers.computer.scroll(
                self._sid,
                x=getattr(action, "x", 640),
                y=getattr(action, "y", 360),
                delta_x=0,
                delta_y=getattr(action, "scroll_y", 0),
            )

        elif t == "hscroll":
            await self._k.browsers.computer.scroll(
                self._sid,
                x=getattr(action, "x", 640),
                y=getattr(action, "y", 360),
                delta_x=getattr(action, "scroll_x", 0),
                delta_y=0,
            )

        elif t == "drag":
            await self._k.browsers.computer.drag_mouse(
                self._sid,
                path=[[action.x, action.y], [action.end_x, action.end_y]],
            )

        elif t == "navigate":
            await self._k.browsers.playwright.execute(
                self._sid,
                code=f"await page.goto({getattr(action, 'url', '')!r}); "
                     "await page.waitForLoadState('networkidle');",
            )

        elif t == "wait":
            await asyncio.sleep(2)


# ── Lightcone OS backend ──────────────────────────────────────────────────────

class LightconeOSBackend:
    """
    CUA backend that controls a Lightcone cloud Linux desktop.

    Uses the Responses API (lc.responses.create) for model decisions and
    lc.computers.METHOD(computer_id, ...) for action execution — consistent
    with the CUA protocol described at docs.lightcone.ai/guides/cua-protocol/.
    """

    def __init__(self, lc_sdk: Any, computer_id: str, width: int = 1280, height: int = 720) -> None:
        self._lc = lc_sdk
        self._cid = computer_id
        self._w = width
        self._h = height

    def _px(self, x: float, y: float) -> tuple[int, int]:
        """Denormalize 0-999 model coordinates → pixel coordinates."""
        return int(x / 1000 * self._w), int(y / 1000 * self._h)

    async def screenshot_b64(self) -> str:
        raw = await self._lc.computers.screenshot(self._cid, base64=True)
        result = getattr(raw, "result", None)
        # result can be a bare base64 string, a data-URI, or a dict {"image": "..."}
        # SDK returns ActionResult where result is {"screenshot_url": "<base64 jpeg>"}
        if isinstance(result, dict):
            b64 = (
                result.get("screenshot_url")
                or result.get("image")
                or result.get("data")
                or result.get("b64")
                or ""
            )
        else:
            b64 = result or ""
        if isinstance(b64, str) and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        return b64 or ""

    async def execute_action(self, action: Any) -> None:
        t = getattr(action, "type", "")
        cid = self._cid

        if t == "click":
            x, y = self._px(action.x, action.y)
            await self._lc.computers.click(cid, x=x, y=y)

        elif t == "double_click":
            x, y = self._px(action.x, action.y)
            await self._lc.computers.double_click(cid, x=x, y=y)

        elif t == "right_click":
            x, y = self._px(action.x, action.y)
            await self._lc.computers.right_click(cid, x=x, y=y)

        elif t == "type":
            await self._lc.computers.type(cid, text=action.text)

        elif t in ("key", "keypress"):
            keys = action.keys if isinstance(action.keys, list) else [action.keys]
            await self._lc.computers.hotkey(cid, keys=keys)

        elif t == "scroll":
            x, y = self._px(getattr(action, "x", 500), getattr(action, "y", 500))
            await self._lc.computers.scroll(cid, x=x, y=y, dx=0, dy=getattr(action, "scroll_y", 0))

        elif t == "hscroll":
            x, y = self._px(getattr(action, "x", 500), getattr(action, "y", 500))
            await self._lc.computers.scroll(cid, x=x, y=y, dx=getattr(action, "scroll_x", 0), dy=0)

        elif t == "drag":
            x, y = self._px(action.x, action.y)
            ex, ey = self._px(action.end_x, action.end_y)
            await self._lc.computers.drag(cid, x=x, y=y, end_x=ex, end_y=ey)

        elif t == "navigate":
            await self._lc.computers.navigate(cid, url=getattr(action, "url", ""))

        elif t == "wait":
            await asyncio.sleep(2)


# ── Local CUA backend ─────────────────────────────────────────────────────────

class LocalCUABackend:
    """
    CUA backend that controls the user's own machine.

    Requires the ComputerFlow local agent to be running (started automatically
    by the desktop app). The local agent exposes a tiny HTTP server on
    localhost:27182 that accepts screenshot and action requests so this class
    can stay async/non-blocking.

    Falls back gracefully if the local agent is unreachable.
    """

    LOCAL_AGENT_URL = "http://localhost:27182"

    async def screenshot_b64(self) -> str:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.LOCAL_AGENT_URL}/screenshot") as r:
                data = await r.json()
                return data["b64"]

    async def execute_action(self, action: Any) -> None:
        import aiohttp
        payload: dict = {"type": getattr(action, "type", "")}

        t = payload["type"]
        if t in ("click", "double_click", "right_click", "drag"):
            payload.update(x=action.x, y=action.y)
            if t == "drag":
                payload.update(end_x=action.end_x, end_y=action.end_y)
        elif t == "type":
            payload["text"] = action.text
        elif t in ("key", "keypress"):
            payload["keys"] = action.keys if isinstance(action.keys, list) else [action.keys]
        elif t in ("scroll", "hscroll"):
            payload.update(
                x=getattr(action, "x", 640),
                y=getattr(action, "y", 360),
                scroll_x=getattr(action, "scroll_x", 0),
                scroll_y=getattr(action, "scroll_y", 0),
            )

        async with aiohttp.ClientSession() as s:
            await s.post(f"{self.LOCAL_AGENT_URL}/action", json=payload)


# ── CUA loop (shared across all backends) ────────────────────────────────────

def _save_frame(b64: str, shots_dir: str, label: str, step_i: int, frame_i: int) -> str:
    """Write a single b64 frame to disk immediately. Returns the saved path."""
    import base64 as _b64, os as _os
    ext = "jpg" if b64.startswith("/9j/") else "png"
    fname = f"{label}_step{step_i:02d}_frame{frame_i:03d}.{ext}"
    path = _os.path.join(shots_dir, fname)
    with open(path, "wb") as f:
        f.write(_b64.b64decode(b64))
    return path


async def _run_cua_loop(
    lc_sdk: Any,
    backend: CUABackend,
    initial_content: list[dict],
    model: str,
    width: int,
    height: int,
    environment: str,
    max_actions: int,
    step_delay_ms: int,
    screenshots: list[str] | None = None,  # kept for compat; frames also saved to disk immediately
    shots_dir: str | None = None,   # if set, every frame is written to disk as captured
    shots_label: str = "session",   # filename prefix
    shots_step: int = 0,            # step index for filename
    on_event: "Callable[[dict], None] | None" = None,  # optional: called per action/screenshot
    debug_log: "Callable[[dict], None] | None" = None,  # optional: called per CUA request/response
) -> tuple[str, int, list[Any]]:
    """
    Core CUA protocol loop — identical for all three backends.

    Sends initial_content to Northstar, then loops:
      screenshot → model → action → execute → repeat

    Returns (answer, actions_taken, events).
    Every screenshot is written to shots_dir immediately on capture (not buffered).
    """
    computer_tool = {
        "type": "computer_use",
        "display_width": width,
        "display_height": height,
        "environment": environment,
    }

    # Debug: log the initial prompt + response
    if debug_log:
        try:
            debug_log({
                "phase": "initial_request",
                "model": model,
                "environment": environment,
                "display": [width, height],
                "content": _redact_images(initial_content),
            })
        except Exception:
            pass

    response = await lc_sdk.responses.create(
        model=model,
        input=[{"role": "user", "content": initial_content}],
        tools=[computer_tool],
    )

    if debug_log:
        try:
            debug_log({
                "phase": "initial_response",
                "response_id": getattr(response, "id", None),
                "output": _summarise_response_output(response),
            })
        except Exception:
            pass

    answer = ""
    actions_taken = 0
    events: list[Any] = []

    for _ in range(max_actions):
        # Find the computer_call in the response output
        computer_call = None
        for block in getattr(response, "output", []) or []:
            if getattr(block, "type", "") == "computer_call":
                computer_call = block
                break

        if not computer_call:
            answer = _extract_text(response)
            break

        action = computer_call.action
        action_type = getattr(action, "type", "unknown")
        events.append({"action": action_type})
        if on_event:
            try:
                on_event({"type": "action", "action": action_type, "environment": environment})
            except Exception:
                pass

        if action_type in ("terminate", "done", "answer"):
            answer = (
                getattr(action, "text", "")
                or getattr(action, "answer", "")
                or getattr(action, "result", "")
                or _extract_text(response)
            )
            break

        await backend.execute_action(action)
        actions_taken += 1
        await asyncio.sleep(step_delay_ms / 1000)

        b64 = await backend.screenshot_b64()
        if screenshots is not None:
            screenshots.append(b64)
        if shots_dir and b64:
            # use list length as frame index so CUA frames slot in among poller frames
            fi = (len(screenshots) - 1) if screenshots is not None else actions_taken
            _save_frame(b64, shots_dir, shots_label, shots_step, fi)
        if on_event and b64 and environment != "browser":
            # Emit screenshots only for desktop (CUA) runs — browser has live view URL instead
            try:
                on_event({"type": "screenshot", "b64": b64, "environment": environment})
            except Exception:
                pass

        if debug_log:
            try:
                debug_log({
                    "phase": "action_executed",
                    "action_type": action_type,
                    "action_detail": _safe_action_dict(action),
                    "actions_taken": actions_taken,
                })
            except Exception:
                pass

        mime = "image/jpeg" if b64.startswith("/9j/") else "image/png"
        response = await lc_sdk.responses.create(
            model=model,
            previous_response_id=response.id,
            input=[{
                "type": "computer_call_output",
                "call_id": computer_call.call_id,
                "output": {
                    "type": "input_image",
                    "image_url": f"data:{mime};base64,{b64}",
                    "detail": "auto",
                },
            }],
            tools=[computer_tool],
        )

        if debug_log:
            try:
                debug_log({
                    "phase": "loop_response",
                    "response_id": getattr(response, "id", None),
                    "output": _summarise_response_output(response),
                })
            except Exception:
                pass

    answer = answer or _extract_text(response)
    return answer, actions_taken, events


def _redact_images(content: Any) -> Any:
    """Remove base64 image blobs from logged content — keep just a marker."""
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, dict):
                c = dict(item)
                url = c.get("image_url")
                if isinstance(url, str) and url.startswith("data:image/"):
                    c["image_url"] = f"<base64 image, {len(url)} chars>"
                elif isinstance(url, dict) and isinstance(url.get("url"), str) and url["url"].startswith("data:image/"):
                    c["image_url"] = {"url": f"<base64 image, {len(url['url'])} chars>"}
                out.append(c)
            else:
                out.append(item)
        return out
    return content


def _summarise_response_output(response: Any) -> list[dict]:
    """Flatten response output to a JSON-serialisable summary."""
    out: list[dict] = []
    for block in getattr(response, "output", []) or []:
        btype = getattr(block, "type", "?")
        if btype == "computer_call":
            action = getattr(block, "action", None)
            out.append({
                "type": "computer_call",
                "call_id": getattr(block, "call_id", None),
                "action": _safe_action_dict(action),
            })
        elif btype == "text":
            out.append({"type": "text", "text": getattr(block, "text", "")[:500]})
        elif btype == "message":
            content = getattr(block, "content", None)
            if isinstance(content, str):
                out.append({"type": "message", "text": content[:500]})
            elif isinstance(content, list):
                snippets = []
                for c in content:
                    txt = getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else None)
                    if txt: snippets.append(str(txt)[:300])
                out.append({"type": "message", "snippets": snippets})
        else:
            out.append({"type": btype})
    return out


def _safe_action_dict(action: Any) -> dict:
    """Extract action fields to a plain dict."""
    if action is None:
        return {}
    keys = ["type", "x", "y", "text", "keys", "button", "scroll_x", "scroll_y", "path", "url"]
    d: dict = {}
    for k in keys:
        v = getattr(action, k, None)
        if v is not None:
            d[k] = v
    return d


def _extract_text(response: Any) -> str:
    for block in getattr(response, "output", []) or []:
        block_type = getattr(block, "type", "")
        if block_type == "text":
            return getattr(block, "text", "")
        if block_type == "message":
            content = getattr(block, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    str(getattr(c, "text", None) or getattr(c, "content", None) or "")
                    for c in content
                    if getattr(c, "text", None) or getattr(c, "content", None)
                ]
                if parts:
                    return "\n".join(parts)
    return ""


# ── Runner ────────────────────────────────────────────────────────────────────

class ComputerFlowRunner:
    """
    Single entry point for all ComputerFlow task execution.

    Reads API keys from environment:
        KERNEL_API_KEY          — required for KERNEL_BROWSER target
        TZAFON_API_KEY          — required for LIGHTCONE_OS target and CUA decisions
        LIGHTCONE_API_KEY       — alias for TZAFON_API_KEY
    """

    MODEL = "tzafon.northstar-cua-fast"

    def __init__(
        self,
        kernel_api_key: str | None = None,
        lightcone_api_key: str | None = None,
        open_live_views: bool = False,
    ) -> None:
        self._kernel_key = kernel_api_key or os.environ.get("KERNEL_API_KEY")
        self._lightcone_key = (
            lightcone_api_key
            or os.environ.get("TZAFON_API_KEY")
            or os.environ.get("LIGHTCONE_API_KEY")
        )
        self._open_live_views = open_live_views

    # ── Primary entry point ───────────────────────────────────────────────────

    async def run_flow(
        self,
        flow: FlowRequest,
        on_event: "Callable[[dict], None] | None" = None,
        debug_log: "Callable[[dict], None] | None" = None,
    ) -> FlowResult:
        """
        Execute a full flow, handling target routing and handoffs automatically.

        Steps are grouped into contiguous runs by (target, strategy).
        When the target changes between steps a session handoff occurs —
        the previous session stays open so it can receive future steps if the
        flow toggles back.

        If on_event is provided, it's called with:
          {"type": "live_view", "urls": {...}}  — as soon as URLs are known
          {"type": "action", "action": "click", ...} — per CUA action
          {"type": "screenshot", "b64": "...", "environment": "desktop"} — CUA frames

        Returns a FlowResult with answer, step count, and live_view_urls for
        every surface used (frontend surfaces these to the user).
        """
        try:
            return await self._execute_flow(flow, on_event=on_event, debug_log=debug_log)
        except Exception as exc:
            return FlowResult(answer="", steps_taken=0, ok=False, error=str(exc))

    # ── Flow execution ────────────────────────────────────────────────────────

    async def _execute_flow(
        self,
        flow: FlowRequest,
        on_event: "Callable[[dict], None] | None" = None,
        debug_log: "Callable[[dict], None] | None" = None,
    ) -> FlowResult:
        opts = flow.options
        live_view_urls: dict[str, str] = {}
        all_events: list[Any] = []
        total_steps = 0
        answer = ""
        env_id: str | None = opts.environment_id

        # Lazy-created SDK clients and open sessions (kept across handoffs)
        kernel_sdk: Any = None
        lc_sdk: Any = None
        kernel_session_id: str | None = None
        kernel_replay_id: str | None = None
        lightcone_computer_id: str | None = None

        try:
            # Group consecutive steps by (target, strategy) to batch them
            groups = _group_steps(flow)

            for group_target, group_strategy, group_steps in groups:
                # ── AUTONOMOUS ──────────────────────────────────────────────
                if group_strategy == ExecutionStrategy.AUTONOMOUS:
                    lc_sdk = lc_sdk or _make_lc(self._lightcone_key)
                    prompt = _steps_to_prompt(flow, group_steps)
                    kind = (
                        "browser"
                        if group_target == RunTarget.KERNEL_BROWSER
                        else "desktop"
                    )
                    from app.infra.lightcone import LightconeClient
                    lc_client = LightconeClient(api_key=self._lightcone_key)
                    result = await lc_client.run_task_collect(
                        instruction=prompt,
                        kind=kind,
                        max_steps=opts.max_total_actions,
                        environment_id=env_id,
                        verbose=True,
                    )
                    answer = result.answer or answer
                    total_steps += result.steps
                    all_events.extend(result.events)
                    continue

                # ── DIRECT (replay without model) ────────────────────────────
                if group_strategy == ExecutionStrategy.DIRECT:
                    for step in group_steps:
                        await self._execute_step_direct(
                            step, group_target, kernel_sdk, kernel_session_id,
                            lc_sdk, lightcone_computer_id, opts
                        )
                        total_steps += 1
                    continue

                # ── CUA LOOP ─────────────────────────────────────────────────
                if group_target == RunTarget.KERNEL_BROWSER:
                    # Ensure Kernel session exists
                    if kernel_sdk is None:
                        from kernel import AsyncKernel
                        kernel_sdk = AsyncKernel(api_key=self._kernel_key)
                    if kernel_session_id is None:
                        sess = await kernel_sdk.browsers.create(
                            stealth=opts.stealth,
                            viewport={"width": opts.viewport_width, "height": opts.viewport_height},
                        )
                        kernel_session_id = sess.session_id
                        url = getattr(sess, "browser_live_view_url", None) or ""
                        if url:
                            live_view_urls["kernel_browser"] = url
                            if on_event:
                                try:
                                    on_event({"type": "live_view", "urls": dict(live_view_urls)})
                                except Exception:
                                    pass
                        print(f"[kernel] browser {kernel_session_id} (live: {url})")
                        if url and self._open_live_views:
                            import subprocess as _sp
                            _sp.Popen(["open", url])

                        # Start replay recording
                        try:
                            replay = await kernel_sdk.browsers.replays.start(kernel_session_id)
                            kernel_replay_id = replay.replay_id
                            print(f"[kernel] replay recording started: {kernel_replay_id}")
                        except Exception as e:
                            print(f"[kernel] replay start failed (non-fatal): {e}")

                    if lc_sdk is None:
                        lc_sdk = _make_lc(self._lightcone_key)

                    # Navigate to start URL on first browser group
                    if flow.start_url and not live_view_urls.get("_browser_started"):
                        await kernel_sdk.browsers.playwright.execute(
                            kernel_session_id,
                            code=f"await page.goto({flow.start_url!r}); "
                                 "await page.waitForLoadState('networkidle');",
                        )
                        await asyncio.sleep(1.0)
                        live_view_urls["_browser_started"] = "1"

                    backend = KernelBrowserBackend(kernel_sdk, kernel_session_id)
                    ans, n, evs = await self._run_group_cua(
                        lc_sdk, backend, flow, group_steps, opts,
                        environment="browser",
                        session_label=f"kernel_{kernel_session_id[-8:]}",
                        on_event=on_event,
                    )

                elif group_target == RunTarget.LIGHTCONE_OS:
                    if lc_sdk is None:
                        lc_sdk = _make_lc(self._lightcone_key)
                    if lightcone_computer_id is None:
                        raw = await lc_sdk.computers.create(
                            kind="desktop",
                            persistent=opts.environment_id is not None,
                            **( {"environment_id": env_id} if env_id else {} ),
                        )
                        lightcone_computer_id = raw.id
                        env_id = env_id or raw.id
                        endpoints = getattr(raw, "endpoints", {}) or {}
                        debug_path = endpoints.get("debug")
                        if debug_path:
                            live_view_urls["lightcone_os"] = f"https://api.tzafon.ai{debug_path}"
                            if on_event:
                                try:
                                    on_event({"type": "live_view", "urls": dict(live_view_urls)})
                                except Exception:
                                    pass
                        lc_live = live_view_urls.get("lightcone_os", "")
                        print(f"[lightcone] computer {lightcone_computer_id} (live: {lc_live})")
                        if lc_live and self._open_live_views:
                            import subprocess as _sp
                            print(f"[lightcone] opening live view in browser...")
                            _sp.Popen(["open", lc_live])

                    backend = LightconeOSBackend(lc_sdk, lightcone_computer_id, opts.viewport_width, opts.viewport_height)
                    ans, n, evs = await self._run_group_cua(
                        lc_sdk, backend, flow, group_steps, opts,
                        environment="desktop",
                        session_label=f"lightcone_{lightcone_computer_id[-8:]}",
                        on_event=on_event,
                    )

                elif group_target == RunTarget.LOCAL:
                    if lc_sdk is None:
                        lc_sdk = _make_lc(self._lightcone_key)
                    backend = LocalCUABackend()
                    ans, n, evs = await self._run_group_cua(
                        lc_sdk, backend, flow, group_steps, opts,
                        environment="desktop",
                        session_label="local",
                        on_event=on_event,
                    )
                else:
                    raise ValueError(f"Unhandled target: {group_target!r}")

                answer = ans or answer
                total_steps += n
                all_events.extend(evs)

        finally:
            # Clean up sessions
            if kernel_session_id and kernel_sdk:
                if kernel_replay_id:
                    try:
                        await kernel_sdk.browsers.replays.stop(
                            replay_id=kernel_replay_id,
                            id=kernel_session_id,
                        )
                        print(f"[kernel] replay stopped: {kernel_replay_id}")
                    except Exception as e:
                        print(f"[kernel] replay stop failed (non-fatal): {e}")
                try:
                    await kernel_sdk.browsers.delete_by_id(kernel_session_id)
                    print(f"[kernel] session {kernel_session_id} deleted")
                except Exception:
                    pass
            if lightcone_computer_id and lc_sdk:
                # Capture final screenshot before deletion so the result is verifiable
                try:
                    raw_shot = await lc_sdk.computers.screenshot(lightcone_computer_id, base64=True)
                    result_field = getattr(raw_shot, "result", None)
                    b64 = (
                        result_field.get("screenshot_url") if isinstance(result_field, dict)
                        else result_field
                    ) or ""
                    if b64:
                        import base64 as _b64, os as _os, subprocess as _sp
                        shot_path = _os.path.join(
                            _os.path.dirname(_os.path.abspath(__file__)),
                            f"../../../screenshots/lightcone_final_{lightcone_computer_id[-8:]}.jpg"
                        )
                        shot_path = _os.path.normpath(shot_path)
                        _os.makedirs(_os.path.dirname(shot_path), exist_ok=True)
                        with open(shot_path, "wb") as f:
                            f.write(_b64.b64decode(b64))
                        print(f"[lightcone] final screenshot → {shot_path}")
                        if self._open_live_views:
                            _sp.Popen(["open", shot_path])
                except Exception as e:
                    print(f"[lightcone] screenshot failed (non-fatal): {e}")

                if not opts.environment_id:
                    try:
                        await lc_sdk.computers.delete(lightcone_computer_id)
                        print(f"[lightcone] computer {lightcone_computer_id} deleted")
                    except Exception:
                        pass

        live_view_urls.pop("_browser_started", None)
        return FlowResult(
            answer=answer,
            steps_taken=total_steps,
            live_view_urls=live_view_urls,
            environment_id=env_id,
            replay_id=kernel_replay_id,
            events=all_events,
        )

    async def _run_group_cua(
        self,
        lc_sdk: Any,
        backend: CUABackend,
        flow: FlowRequest,
        steps: list[SOPStep],
        opts: RunOptions,
        environment: str,
        session_label: str = "",
        on_event: "Callable[[dict], None] | None" = None,
        debug_log: "Callable[[dict], None] | None" = None,
    ) -> tuple[str, int, list[Any]]:
        """
        Run a group of steps via the CUA loop on a given backend.

        Every screenshot captured during the loop is saved to
        screenshots/<label>_step<N>_action<M>.jpg so you can verify
        what happened at each step without a live viewer.
        """
        import base64 as _b64, os as _os, subprocess as _sp

        shots_dir = _os.path.normpath(
            _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "../../../screenshots")
        )
        _os.makedirs(shots_dir, exist_ok=True)

        total_answer = ""
        total_actions = 0
        total_events: list[Any] = []

        for step_i, step in enumerate(steps):
            print(f"  [cua] {step.intent[:80]}")
            if on_event:
                try:
                    on_event({
                        "type": "step",
                        "stepIndex": step_i,
                        "totalSteps": len(steps),
                        "intent": step.intent,
                        "environment": environment,
                    })
                except Exception:
                    pass

            if (
                environment == "browser"
                and step.action == ActionType.NAVIGATE
                and step.text
                and isinstance(backend, KernelBrowserBackend)
            ):
                print(f"  [playwright] → {step.text}")
                await backend._k.browsers.playwright.execute(
                    backend._sid,
                    code=(
                        f"await page.goto({step.text!r}); "
                        "await page.waitForLoadState('networkidle');"
                    ),
                )
                await asyncio.sleep(1.5)

            label = session_label or environment
            # open folder immediately so user can watch frames appear live
            if self._open_live_views:
                _sp.Popen(["open", shots_dir])

            live_b64 = await backend.screenshot_b64()
            content = _build_step_content(
                step, live_b64,
                workflow_summary=flow.context or "",
                workflow_app=flow.app,
                workflow_start_url=flow.start_url or "",
                workflow_alternatives=flow.alternatives,
            )

            # Seed list and save initial frame immediately
            step_shots: list[str] = [live_b64]
            _save_frame(live_b64, shots_dir, label, step_i, 0)
            if on_event and live_b64 and environment != "browser":
                try:
                    on_event({"type": "screenshot", "b64": live_b64, "environment": environment})
                except Exception:
                    pass

            # For Lightcone OS: background poller captures frames every 3s during
            # slow operations (app launch, installs) between CUA actions.
            poller_task = None
            if isinstance(backend, LightconeOSBackend):
                async def _poll_screenshots(b: LightconeOSBackend, out: list[str],
                                            sd: str, lbl: str, si: int) -> None:
                    while True:
                        await asyncio.sleep(3)
                        try:
                            b64 = await b.screenshot_b64()
                            if b64 and (not out or b64 != out[-1]):
                                fi = len(out)
                                out.append(b64)
                                _save_frame(b64, sd, lbl, si, fi)
                        except Exception:
                            pass
                poller_task = asyncio.create_task(
                    _poll_screenshots(backend, step_shots, shots_dir, label, step_i)
                )

            # Retry step up to 3 times on exception; the CUA itself handles most
            # soft failures internally, so retries kick in for network/SDK errors.
            MAX_STEP_RETRIES = 3
            ans, n, evs = "", 0, []
            last_error: Exception | None = None
            try:
                for attempt in range(MAX_STEP_RETRIES):
                    try:
                        if attempt > 0:
                            print(f"  [cua] retry {attempt}/{MAX_STEP_RETRIES - 1} for step {step_i}")
                            if on_event:
                                try:
                                    on_event({"type": "retry", "stepIndex": step_i, "attempt": attempt})
                                except Exception:
                                    pass
                            # Refresh screenshot + content before retrying
                            live_b64 = await backend.screenshot_b64()
                            content = _build_step_content(
                step, live_b64,
                workflow_summary=flow.context or "",
                workflow_app=flow.app,
                workflow_start_url=flow.start_url or "",
                workflow_alternatives=flow.alternatives,
            )
                        ans, n, evs = await _run_cua_loop(
                            lc_sdk=lc_sdk,
                            backend=backend,
                            initial_content=content,
                            model=self.MODEL,
                            width=opts.viewport_width,
                            height=opts.viewport_height,
                            environment=environment,
                            max_actions=opts.max_actions_per_step,
                            step_delay_ms=opts.step_delay_ms,
                            screenshots=step_shots,
                            shots_dir=shots_dir,
                            shots_label=label,
                            shots_step=step_i,
                            on_event=on_event,
                        )
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        print(f"  [cua] step {step_i} attempt {attempt + 1} failed: {e}")
                        await asyncio.sleep(1.5 * (attempt + 1))
                if last_error is not None:
                    raise last_error
            finally:
                if poller_task:
                    poller_task.cancel()
                    try:
                        await poller_task
                    except asyncio.CancelledError:
                        pass

            print(f"  [screenshots] {len(step_shots)} frames saved → screenshots/{label}_step{step_i:02d}_*")

            total_answer = ans or total_answer
            total_actions += n
            total_events.extend(evs)

            if step.wait_ms:
                await asyncio.sleep(step.wait_ms / 1000)

        return total_answer, total_actions, total_events

    async def _execute_step_direct(
        self,
        step: SOPStep,
        target: RunTarget,
        kernel_sdk: Any,
        kernel_session_id: str | None,
        lc_sdk: Any,
        lightcone_computer_id: str | None,
        opts: RunOptions,
    ) -> None:
        """Execute a step directly from its recorded coordinates (no model call)."""
        if target == RunTarget.KERNEL_BROWSER and kernel_session_id:
            backend = KernelBrowserBackend(kernel_sdk, kernel_session_id)
        elif target == RunTarget.LIGHTCONE_OS and lightcone_computer_id:
            backend = LightconeOSBackend(lc_sdk, lightcone_computer_id, opts.viewport_width, opts.viewport_height)
        elif target == RunTarget.LOCAL:
            backend = LocalCUABackend()
        else:
            return

        # Build a synthetic action-like namespace from the step fields
        import types as _t
        action = _t.SimpleNamespace(
            type=step.action.value,
            x=step.x,
            y=step.y,
            end_x=step.end_x,
            end_y=step.end_y,
            text=step.text,
            keys=step.keys,
            scroll_x=step.dx,
            scroll_y=step.dy,
            url=step.text if step.action == ActionType.NAVIGATE else None,
        )
        await backend.execute_action(action)
        if step.wait_ms:
            await asyncio.sleep(step.wait_ms / 1000)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_lc(key: str | None) -> Any:
    if not key:
        raise ValueError(
            "TZAFON_API_KEY is required for Lightcone OS and CUA model decisions."
        )
    from tzafon import AsyncLightcone
    return AsyncLightcone(api_key=key)


def _group_steps(
    flow: FlowRequest,
) -> list[tuple[RunTarget, ExecutionStrategy, list[SOPStep]]]:
    """
    Group consecutive steps that share the same (resolved_target, strategy).
    Each group becomes one session or one prompt.
    """
    if not flow.steps:
        return []

    groups: list[tuple[RunTarget, ExecutionStrategy, list[SOPStep]]] = []
    current_target = flow.resolved_target(flow.steps[0])
    current_strategy = flow.resolved_strategy(flow.steps[0])
    current_group: list[SOPStep] = []

    for step in flow.steps:
        t = flow.resolved_target(step)
        s = flow.resolved_strategy(step)
        if t == current_target and s == current_strategy:
            current_group.append(step)
        else:
            groups.append((current_target, current_strategy, current_group))
            current_target, current_strategy, current_group = t, s, [step]

    groups.append((current_target, current_strategy, current_group))
    return groups


def _steps_to_prompt(flow: FlowRequest, steps: list[SOPStep]) -> str:
    """Flatten a subset of steps to a natural-language task prompt."""
    parts = []
    if flow.context:
        parts.append(flow.context.strip())
    if flow.start_url:
        parts.append(f"Start at: {flow.start_url}")
    parts.append(f"Goal: {flow.goal}")
    parts.append("Steps:")
    for i, step in enumerate(steps, 1):
        line = f"  {i}. {step.intent}"
        if step.action == ActionType.NAVIGATE and step.text:
            line += f" → {step.text}"
        elif step.action == ActionType.TYPE and step.text:
            line += f' → type "{step.text}"'
        elif step.action == ActionType.HOTKEY and step.keys:
            line += f" → {'+'.join(step.keys)}"
        parts.append(line)
    return "\n".join(parts)


def _build_step_content(
    step: SOPStep,
    live_b64: str,
    workflow_summary: str = "",
    workflow_app: str = "",
    workflow_start_url: str = "",
    workflow_alternatives: list[str] | None = None,
) -> list[dict]:
    """
    Build the `content` array for one CUA loop iteration.

    Always includes:
      - (optional) The workflow-level high-level summary
      - The step instruction text
      - The current live screenshot

    Also includes (when available):
      - The reference screenshot from the recording
      - A note describing the annotation (bounding box)
    """
    instruction = ""
    if workflow_summary:
        instruction += f"OVERALL GOAL (top priority): {workflow_summary}\n"
    if workflow_app:
        instruction += f"APP: The workflow runs inside '{workflow_app}'. If the app is not already open/focused, open/focus it first.\n"
    if workflow_start_url:
        instruction += f"START URL: The workflow starts at {workflow_start_url}. If you aren't already on that URL (or a compatible one), navigate there before doing the first step.\n"
    if workflow_alternatives:
        instruction += "ALTERNATIVE STRATEGIES (use if the recorded path fails):\n"
        for alt in workflow_alternatives[:5]:
            instruction += f"  - {alt}\n"
    if workflow_summary or workflow_app or workflow_start_url or workflow_alternatives:
        instruction += (
            "\nIMPORTANT: The overall goal takes PRIORITY over the exact recorded steps. "
            "The steps below were captured from a user demo and are a reference, not a strict script. "
            "You are allowed — and expected — to DEVIATE from the steps when doing so better achieves the goal. "
            "Skip redundant steps, retry failed actions, adapt to UI differences, and fall back to the alternative strategies above when the obvious path fails. "
            "Only follow a step literally when it is the best way forward.\n\n"
        )
    instruction += f"CURRENT STEP (reference — may deviate if needed): {step.intent}"
    if step.action == ActionType.TYPE and step.text:
        instruction += f' Type: "{step.text}"'
    elif step.action == ActionType.NAVIGATE and step.text:
        instruction += f" Navigate to: {step.text}"
    elif step.action == ActionType.HOTKEY and step.keys:
        instruction += f" Press: {'+'.join(step.keys)}"
    elif step.description:
        instruction += f" Target: {step.description}"

    mime = "image/jpeg" if live_b64.startswith("/9j/") else "image/png"
    content: list[dict] = [
        {"type": "input_text", "text": instruction},
        {
            "type": "input_image",
            "image_url": f"data:{mime};base64,{live_b64}",
            "detail": "auto",
        },
    ]

    if step.screenshot_b64:
        note = "Reference screenshot from the recording (use to identify the target element)"
        if step.annotation:
            a = step.annotation
            note += (
                f" — the target is highlighted at "
                f"x={a.get('x')}, y={a.get('y')}, "
                f"w={a.get('w')}, h={a.get('h')}"
            )
        content.append({"type": "input_text", "text": note + ":"})
        content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{step.screenshot_b64}",
            "detail": "auto",
        })

    return content
