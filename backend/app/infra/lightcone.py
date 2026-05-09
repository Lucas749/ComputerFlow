"""
Lightcone / Tzafon Northstar infrastructure client — fully async.

Two distinct interaction layers:

  ComputerSession  (low-level)
    Direct control of a Lightcone OS computer instance.
    Every action (click, type, scroll, screenshot, exec …) is a coroutine.
    Use when you need precise control of every step — e.g. the Responses API loop.

  LightconeClient  (high-level)
    Manages computer lifecycle and wraps the autonomous Task API so Northstar
    drives the computer itself from a natural-language instruction.
    Supports persistent environments, batch runs, and cross-app workflows.

SDK note
--------
tzafon SDK reads TZAFON_API_KEY (alias: LIGHTCONE_API_KEY).
All computer actions are on lc.computers.METHOD(computer_id, **kwargs),
not methods on the computer object itself.

Live view
---------
Every ComputerSession exposes .live_view_url — open in any browser to watch
in real time.  Built from the 'debug' endpoint in the computer's endpoints dict.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, AsyncIterator, Literal

TZAFON_BASE = "https://api.tzafon.ai"

ComputerKind = Literal["desktop", "browser"]


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ScreenshotResult:
    raw: Any
    b64: str | None = None          # base64 PNG (no data-URI prefix)
    page_context: Any | None = None # url, title, viewport dims

    @property
    def image_b64(self) -> str:
        if self.b64:
            s = self.b64
            return s.split(",", 1)[1] if s.startswith("data:") else s
        raise RuntimeError("Screenshot returned no image data")


@dataclass
class ActionResult:
    status: str
    result: Any = None
    page_context: Any | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success" and not self.error_message


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class TaskEvent:
    raw: Any
    kind: str = ""
    message: str = ""
    step: int = 0


@dataclass
class AgentResult:
    answer: str
    steps: int
    events: list[Any] = field(default_factory=list)


@dataclass
class TaskHandle:
    task_id: str
    _client: "LightconeClient" = field(repr=False)

    async def status(self) -> dict:
        return await self._client.get_task_status(self.task_id)

    async def pause(self) -> None:
        await self._client.pause_task(self.task_id)

    async def resume(self) -> None:
        await self._client.resume_task(self.task_id)

    async def inject(self, message: str) -> None:
        await self._client.inject_task_message(self.task_id, message)


# ── ComputerSession ───────────────────────────────────────────────────────────

class ComputerSession:
    """
    Low-level async wrapper around a live Lightcone OS computer instance.

    All actions delegate to lc.computers.METHOD(self.id, ...) — this is how
    the tzafon SDK works (resource methods, not object methods).
    """

    def __init__(self, raw: Any, sdk: Any) -> None:
        self._raw = raw     # ComputerResponse
        self._sdk = sdk     # AsyncLightcone

    @property
    def id(self) -> str:
        return self._raw.id

    @property
    def kind(self) -> str:
        return getattr(self._raw, "kind", "desktop")

    @property
    def status(self) -> str:
        return getattr(self._raw, "status", "unknown")

    @property
    def live_view_url(self) -> str | None:
        """Open in browser to watch the computer in real time."""
        endpoints = getattr(self._raw, "endpoints", None) or {}
        path = endpoints.get("debug")
        return f"{TZAFON_BASE}{path}" if path else None

    @property
    def screencast_url(self) -> str | None:
        endpoints = getattr(self._raw, "endpoints", None) or {}
        path = endpoints.get("screencast")
        return f"{TZAFON_BASE}{path}" if path else None

    @property
    def endpoints(self) -> dict[str, str]:
        return getattr(self._raw, "endpoints", None) or {}

    # ── Capture ──────────────────────────────────────────────────────────────

    async def screenshot(self) -> ScreenshotResult:
        """Capture the current screen, return base64 PNG."""
        raw = await self._sdk.computers.screenshot(self.id, base64=True)
        b64: str | None = getattr(raw, "result", None)
        return ScreenshotResult(
            raw=raw,
            b64=b64,
            page_context=getattr(raw, "page_context", None),
        )

    async def screenshot_b64(self) -> str:
        """Convenience: return bare base64 string."""
        return (await self.screenshot()).image_b64

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate(self, url: str) -> ActionResult:
        raw = await self._sdk.computers.navigate(self.id, url=url)
        return _wrap_action(raw)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    async def click(self, x: float, y: float) -> ActionResult:
        raw = await self._sdk.computers.click(self.id, x=x, y=y)
        return _wrap_action(raw)

    async def double_click(self, x: float, y: float) -> ActionResult:
        raw = await self._sdk.computers.double_click(self.id, x=x, y=y)
        return _wrap_action(raw)

    async def right_click(self, x: float, y: float) -> ActionResult:
        raw = await self._sdk.computers.right_click(self.id, x=x, y=y)
        return _wrap_action(raw)

    async def scroll(self, x: float, y: float, dx: float = 0, dy: float = -3) -> ActionResult:
        raw = await self._sdk.computers.scroll(self.id, x=x, y=y, dx=dx, dy=dy)
        return _wrap_action(raw)

    async def drag(self, x1: float, y1: float, x2: float, y2: float) -> ActionResult:
        raw = await self._sdk.computers.drag(self.id, x=x1, y=y1, end_x=x2, end_y=y2)
        return _wrap_action(raw)

    async def mouse_down(self, x: float, y: float) -> ActionResult:
        raw = await self._sdk.computers.mouse_down(self.id, x=x, y=y)
        return _wrap_action(raw)

    async def mouse_up(self, x: float, y: float) -> ActionResult:
        raw = await self._sdk.computers.mouse_up(self.id, x=x, y=y)
        return _wrap_action(raw)

    # ── Keyboard ──────────────────────────────────────────────────────────────

    async def type(self, text: str) -> ActionResult:
        raw = await self._sdk.computers.type(self.id, text=text)
        return _wrap_action(raw)

    async def hotkey(self, *keys: str) -> ActionResult:
        """E.g. await sess.hotkey("ctrl", "a") or await sess.hotkey("Return")."""
        raw = await self._sdk.computers.hotkey(self.id, keys=list(keys))
        return _wrap_action(raw)

    async def key_down(self, key: str) -> ActionResult:
        raw = await self._sdk.computers.key_down(self.id, key=key)
        return _wrap_action(raw)

    async def key_up(self, key: str) -> ActionResult:
        raw = await self._sdk.computers.key_up(self.id, key=key)
        return _wrap_action(raw)

    # ── Page info (browser kind) ──────────────────────────────────────────────

    async def html(self) -> str:
        raw = await self._sdk.computers.html(self.id)
        return getattr(raw, "result", "") or ""

    async def viewport(self) -> dict:
        raw = await self._sdk.computers.viewport(self.id)
        ctx = getattr(raw, "page_context", None)
        if ctx and hasattr(ctx, "__dict__"):
            return ctx.__dict__
        return getattr(raw, "result", {}) or {}

    # ── Shell ─────────────────────────────────────────────────────────────────

    async def exec_sync(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
    ) -> ExecResult:
        kwargs: dict = {"command": command}
        if cwd:
            kwargs["cwd"] = cwd
        if env:
            kwargs["env"] = env
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds
        raw = await self._sdk.computers.exec.sync(self.id, **kwargs)
        return ExecResult(
            stdout=getattr(raw, "stdout", "") or "",
            stderr=getattr(raw, "stderr", "") or "",
            exit_code=getattr(raw, "exit_code", 0),
            error_message=getattr(raw, "error_message", None),
        )

    async def exec_stream(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[dict]:
        kwargs: dict = {"command": command}
        if cwd:
            kwargs["cwd"] = cwd
        if env:
            kwargs["env"] = env
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds
        stream = await self._sdk.computers.exec.create(self.id, **kwargs)
        async for chunk in stream:
            yield chunk.__dict__ if hasattr(chunk, "__dict__") else {"raw": chunk}

    # ── Batch ─────────────────────────────────────────────────────────────────

    async def batch(self, actions: list[dict]) -> list[Any]:
        """Execute multiple actions in one round-trip."""
        raw = await self._sdk.computers.batch(self.id, actions)
        return raw if isinstance(raw, list) else [raw]

    # ── Tabs (browser) ────────────────────────────────────────────────────────

    async def list_tabs(self) -> list[Any]:
        raw = await self._sdk.computers.tabs.list(self.id)
        return raw if isinstance(raw, list) else [raw]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def keepalive(self) -> None:
        await self._sdk.computers.keepalive(self.id)

    async def delete(self) -> None:
        try:
            await self._sdk.computers.delete(self.id)
        except Exception:
            pass

    async def __aenter__(self) -> "ComputerSession":
        return self

    async def __aexit__(self, *_) -> None:
        await self.delete()


# ── LightconeClient ───────────────────────────────────────────────────────────

class LightconeClient:
    """
    High-level async client for all Lightcone / Tzafon Northstar operations.

    Reads TZAFON_API_KEY (or LIGHTCONE_API_KEY) from the environment.
    """

    def __init__(self, api_key: str | None = None) -> None:
        key = (
            api_key
            or os.environ.get("TZAFON_API_KEY")
            or os.environ.get("LIGHTCONE_API_KEY")
        )
        if not key:
            raise ValueError(
                "TZAFON_API_KEY not set. Pass api_key= or set the environment variable."
            )
        from tzafon import AsyncLightcone
        self._sdk = AsyncLightcone(api_key=key)

    # ── Computers ─────────────────────────────────────────────────────────────

    async def create_computer(
        self,
        kind: ComputerKind = "desktop",
        persistent: bool = False,
        environment_id: str | None = None,
        max_lifetime_seconds: int | None = None,
    ) -> ComputerSession:
        """
        Provision a new Lightcone OS computer.

        kind="desktop"   → full desktop, native apps, multi-window
        kind="browser"   → browser in foreground, optimised for web

        persistent=True  → environment saved after use; reuse via environment_id
        """
        kwargs: dict = {"kind": kind, "persistent": persistent}
        if environment_id:
            kwargs["environment_id"] = environment_id
        if max_lifetime_seconds:
            kwargs["max_lifetime_seconds"] = max_lifetime_seconds
        raw = await self._sdk.computers.create(**kwargs)
        return ComputerSession(raw=raw, sdk=self._sdk)

    async def create_persistent_computer(
        self,
        kind: ComputerKind = "desktop",
        setup_command: str | None = None,
    ) -> ComputerSession:
        """
        Create a persistent environment, optionally running a setup command.
        Returns the session; caller must save session.id as the environment_id
        for future runs.

        Example:
            sess = await client.create_persistent_computer(
                kind="desktop",
                setup_command="apt-get install -y libreoffice",
            )
            env_id = sess.id   # save this
        """
        sess = await self.create_computer(kind=kind, persistent=True)
        if setup_command:
            await sess.exec_sync(setup_command)
        return sess

    @asynccontextmanager
    async def computer(
        self,
        kind: ComputerKind = "desktop",
        persistent: bool = False,
        environment_id: str | None = None,
    ) -> AsyncGenerator[ComputerSession, None]:
        """
        Async context manager — creates and auto-deletes a computer.

            async with client.computer("desktop") as sess:
                print(sess.live_view_url)   # watch in browser
                await sess.navigate("https://example.com")
        """
        sess = await self.create_computer(
            kind=kind, persistent=persistent, environment_id=environment_id
        )
        try:
            yield sess
        finally:
            await sess.delete()

    # ── Tasks — autonomous Northstar ──────────────────────────────────────────

    def run_task(
        self,
        instruction: str,
        kind: ComputerKind = "desktop",
        max_steps: int = 100,
        environment_id: str | None = None,
        model: str = "tzafon.northstar-cua-fast",
        temperature: float = 0.2,
        persistent: bool = False,
    ) -> AsyncIterator[TaskEvent]:
        """
        Run a Northstar task and async-stream events.

            async for event in client.run_task("Open Firefox and go to example.com"):
                print(event.kind, event.message)
        """
        return self._stream_task(
            instruction=instruction,
            kind=kind,
            max_steps=max_steps,
            environment_id=environment_id,
            model=model,
            temperature=temperature,
            persistent=persistent,
        )

    async def _stream_task(self, **kwargs) -> AsyncIterator[TaskEvent]:
        env_id = kwargs.pop("environment_id", None)
        params: dict = {k: v for k, v in kwargs.items()}
        if env_id:
            params["environment_id"] = env_id

        stream = await self._sdk.agent.tasks.start_stream(**params)
        step = 0
        async for raw_event in stream:
            kind_str = (
                getattr(raw_event, "type", "")
                or getattr(raw_event, "kind", "")
                or getattr(raw_event, "event", "")
            )
            msg = (
                getattr(raw_event, "message", "")
                or getattr(raw_event, "text", "")
                or getattr(raw_event, "content", "")
                or ""
            )
            if kind_str in ("action", "step", "computer_call"):
                step += 1
            yield TaskEvent(raw=raw_event, kind=str(kind_str), message=str(msg), step=step)

    async def run_task_collect(
        self,
        instruction: str,
        kind: ComputerKind = "desktop",
        max_steps: int = 100,
        environment_id: str | None = None,
        verbose: bool = True,
    ) -> AgentResult:
        """
        Run a task to completion and return an AgentResult with the final answer.
        Collects all stream events internally.
        """
        events: list[Any] = []
        answer = ""
        async for event in self.run_task(
            instruction, kind=kind, max_steps=max_steps, environment_id=environment_id
        ):
            events.append(event.raw)
            if verbose:
                print(f"  [{event.step:>2}] {event.kind}: {event.message[:80]}")
            if event.kind in ("answer", "done", "result"):
                answer = event.message
        if not answer and events:
            # Fallback: use last message
            last = events[-1]
            answer = (
                getattr(last, "message", "")
                or getattr(last, "text", "")
                or getattr(last, "content", "")
                or ""
            )
        return AgentResult(answer=answer, steps=len(events), events=events)

    async def run_task_on_environment(
        self,
        instruction: str,
        environment_id: str,
        kind: ComputerKind = "desktop",
        max_steps: int = 100,
        verbose: bool = True,
    ) -> AgentResult:
        """
        Run a task inside an existing persistent environment.
        Useful for cross-app workflows where apps are already installed.
        """
        return await self.run_task_collect(
            instruction,
            kind=kind,
            max_steps=max_steps,
            environment_id=environment_id,
            verbose=verbose,
        )

    async def batch_run_tasks(
        self,
        records: list[dict],
        instruction_template: str,
        kind: ComputerKind = "desktop",
        max_steps: int = 30,
        environment_id: str | None = None,
        concurrency: int = 1,
    ) -> list[AgentResult]:
        """
        Run the same task template for each record sequentially (or concurrently).

        instruction_template uses Python str.format(**record), e.g.:
            "Go to https://admin.example.com. Create user {name} with email {email}."

        concurrency=1 (default) runs one record at a time.
        concurrency>1 runs multiple records in parallel (use carefully).

        Example:
            results = await client.batch_run_tasks(
                records=[
                    {"name": "Jane Smith", "email": "jane@acme.com", "role": "Manager"},
                    {"name": "Bob Chen",  "email": "bob@acme.com",  "role": "Engineer"},
                ],
                instruction_template=(
                    "Go to https://admin.example.com/users/new. "
                    "Fill Name: '{name}', Email: '{email}', Role: '{role}'. "
                    "Click Create User."
                ),
                kind="desktop",
            )
        """
        if concurrency == 1:
            results = []
            for i, record in enumerate(records):
                print(f"\n[batch {i+1}/{len(records)}] {record}")
                instruction = instruction_template.format(**record)
                result = await self.run_task_collect(
                    instruction, kind=kind, max_steps=max_steps,
                    environment_id=environment_id,
                )
                results.append(result)
            return results

        # Concurrent execution
        sem = asyncio.Semaphore(concurrency)

        async def _run_one(i: int, record: dict) -> AgentResult:
            async with sem:
                print(f"\n[batch {i+1}/{len(records)}] {record}")
                instruction = instruction_template.format(**record)
                return await self.run_task_collect(
                    instruction, kind=kind, max_steps=max_steps,
                    environment_id=environment_id,
                )

        return list(await asyncio.gather(*[_run_one(i, r) for i, r in enumerate(records)]))

    # ── Task control ──────────────────────────────────────────────────────────

    async def start_task_async(
        self,
        instruction: str,
        kind: ComputerKind = "desktop",
        max_steps: int = 100,
        environment_id: str | None = None,
        model: str = "tzafon.northstar-cua-fast",
    ) -> TaskHandle:
        """Fire-and-forget: returns a TaskHandle for polling / control."""
        kwargs: dict = dict(
            instruction=instruction, kind=kind, max_steps=max_steps, model=model
        )
        if environment_id:
            kwargs["environment_id"] = environment_id
        task = await self._sdk.agent.tasks.start(**kwargs)
        return TaskHandle(task_id=task.task_id, _client=self)

    async def get_task_status(self, task_id: str) -> dict:
        raw = await self._sdk.agent.tasks.retrieve_status(task_id)
        return {"status": getattr(raw, "status", ""), "exit_code": getattr(raw, "exit_code", None)}

    async def pause_task(self, task_id: str) -> None:
        await self._sdk.agent.tasks.pause(task_id)

    async def resume_task(self, task_id: str) -> None:
        await self._sdk.agent.tasks.resume(task_id)

    async def inject_task_message(self, task_id: str, message: str) -> None:
        await self._sdk.agent.tasks.inject_message(task_id, message)

    # ── Responses API (manual CUA loop) ──────────────────────────────────────

    async def responses_create(self, **kwargs) -> Any:
        """
        Direct access to lc.responses.create() for the manual Northstar loop.
        Used by NorthstarKernelAgent.
        """
        return await self._sdk.responses.create(**kwargs)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _wrap_action(raw: Any) -> ActionResult:
    return ActionResult(
        status=getattr(raw, "status", "success") or "success",
        result=getattr(raw, "result", None),
        page_context=getattr(raw, "page_context", None),
        error_message=getattr(raw, "error_message", None),
    )
