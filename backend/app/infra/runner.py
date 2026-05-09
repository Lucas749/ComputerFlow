"""
ComputerFlowRunner — single entry point for all task execution.

This is what the orchestrating model (Claude) calls to replay a user flow.
Pick the right mode for the job; `execute()` accepts a RunConfig and returns
a RunResult with the answer and a live-view URL the UI can surface.

Execution modes
---------------
BROWSER_CUA    Kernel cloud browser + Northstar manual CUA loop.
               Best for: web tasks that need precise step-by-step control,
               tasks with images/annotations marking targets on the page.

DESKTOP_TASK   Lightcone fully-autonomous desktop task.
               Best for: native apps, legacy software, multi-window flows,
               anything that needs a real OS desktop.

BROWSER_TASK   Lightcone fully-autonomous browser task.
               Best for: pure web workflows where you want Northstar to drive
               everything end-to-end without a separate Kernel session.

BATCH          Run the same task template across a list of records.
               Best for: data entry, form filling, bulk operations.

Quickstart
----------
    from app.infra.runner import ComputerFlowRunner, RunConfig, ExecutionMode

    runner = ComputerFlowRunner()

    # One-shot web task
    result = await runner.execute(RunConfig(
        mode=ExecutionMode.BROWSER_CUA,
        task="Go to stripe.com and find the pricing for the Pro plan",
    ))
    print(result.answer)
    print(result.live_view_url)   # hand to UI so user can watch

    # Autonomous desktop task
    result = await runner.execute(RunConfig(
        mode=ExecutionMode.DESKTOP_TASK,
        task="Open LibreOffice, create a new spreadsheet, add 'Hello' in A1, save as /tmp/test.xlsx",
    ))

    # Batch form fill
    results = await runner.run_batch(
        records=[
            {"name": "Alice Chen",  "email": "alice@acme.com", "role": "Manager"},
            {"name": "Bob Patel",   "email": "bob@acme.com",   "role": "Engineer"},
        ],
        instruction_template=(
            "Go to https://admin.example.com/users/new. "
            "Fill Name: '{name}', Email: '{email}', Role: '{role}'. "
            "Click Create User."
        ),
        mode=ExecutionMode.DESKTOP_TASK,
    )
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.infra.types import SOP, Surface


# ── Execution mode ────────────────────────────────────────────────────────────

class ExecutionMode(str, Enum):
    BROWSER_CUA  = "browser_cua"   # Kernel browser + Northstar manual loop
    DESKTOP_TASK = "desktop_task"  # Lightcone autonomous desktop
    BROWSER_TASK = "browser_task"  # Lightcone autonomous browser
    BATCH        = "batch"         # Same template × many records


# ── Config / Result types ─────────────────────────────────────────────────────

@dataclass
class RunConfig:
    """
    Everything needed to run one task.

    Fields
    ------
    mode              Which executor to use (see ExecutionMode).
    task              Natural-language instruction for the agent.
    max_steps         Hard cap on action steps before giving up.
    environment_id    Reuse a persistent Lightcone environment (desktop/browser).
                      Save result.environment_id after the first run to reuse it.
    records           For BATCH mode: list of dicts to interpolate into
                      `instruction_template`.
    instruction_template
                      For BATCH mode: Python str.format(**record) template.
                      E.g. "Create user {name} with email {email}."
    persistent        If True, the Lightcone environment is saved after the run
                      so it can be reused via environment_id next time.
    stealth           For BROWSER_CUA: enable bot-detection bypass.
    concurrency       For BATCH mode: how many records to run in parallel.
    viewport_width    Browser viewport width (BROWSER_CUA / BROWSER_TASK).
    viewport_height   Browser viewport height.
    """
    mode: ExecutionMode
    task: str = ""
    max_steps: int = 50
    environment_id: str | None = None
    records: list[dict] | None = None
    instruction_template: str | None = None
    persistent: bool = False
    stealth: bool = True
    concurrency: int = 1
    viewport_width: int = 1280
    viewport_height: int = 800


@dataclass
class RunResult:
    """
    Outcome of a single task execution.

    Fields
    ------
    answer            The agent's final text answer / summary.
    steps             Number of action steps taken.
    mode              Which executor was used.
    live_view_url     Open this URL in a browser to watch the session in real time.
                      None if the executor doesn't surface one.
    environment_id    If the run used or created a persistent environment, its ID.
                      Save this to pass as RunConfig.environment_id on the next run.
    events            Raw event list from the executor (useful for debugging).
    ok                False if the run ended in an unhandled error.
    error             Error message when ok=False.
    """
    answer: str
    steps: int
    mode: ExecutionMode
    live_view_url: str | None = None
    environment_id: str | None = None
    events: list[Any] = field(default_factory=list)
    ok: bool = True
    error: str | None = None


# ── Runner ────────────────────────────────────────────────────────────────────

class ComputerFlowRunner:
    """
    Single entry point for all ComputerFlow task execution.

    The orchestrating model should instantiate this once and call either
    `execute(config)` for a single task or `run_batch(...)` for bulk work.

    All heavy SDK imports are deferred until the first call so the class
    can be imported cheaply without network calls or auth checks.

    Environment variables read (at least one pair must be set):
        KERNEL_API_KEY     — required for BROWSER_CUA mode
        TZAFON_API_KEY     — required for DESKTOP_TASK / BROWSER_TASK / BATCH
        LIGHTCONE_API_KEY  — alias for TZAFON_API_KEY
    """

    def __init__(
        self,
        kernel_api_key: str | None = None,
        lightcone_api_key: str | None = None,
    ) -> None:
        self._kernel_key = kernel_api_key or os.environ.get("KERNEL_API_KEY")
        self._lightcone_key = (
            lightcone_api_key
            or os.environ.get("TZAFON_API_KEY")
            or os.environ.get("LIGHTCONE_API_KEY")
        )

    # ── Main entry point ──────────────────────────────────────────────────────

    async def execute(self, config: RunConfig) -> RunResult:
        """
        Execute a task according to config.mode.

        This is the primary method the orchestrating model should call.
        Returns a RunResult with `answer` and `live_view_url`.

        Raises ValueError for BATCH mode without records/template.
        Wraps all other errors: result.ok=False, result.error=<message>.
        """
        try:
            if config.mode == ExecutionMode.BROWSER_CUA:
                return await self._run_browser_cua(config)

            if config.mode == ExecutionMode.DESKTOP_TASK:
                return await self._run_lightcone_task(config, kind="desktop")

            if config.mode == ExecutionMode.BROWSER_TASK:
                return await self._run_lightcone_task(config, kind="browser")

            if config.mode == ExecutionMode.BATCH:
                if not config.records or not config.instruction_template:
                    raise ValueError(
                        "BATCH mode requires both RunConfig.records and RunConfig.instruction_template"
                    )
                results = await self.run_batch(
                    records=config.records,
                    instruction_template=config.instruction_template,
                    mode=ExecutionMode.DESKTOP_TASK,
                    max_steps=config.max_steps,
                    environment_id=config.environment_id,
                    concurrency=config.concurrency,
                )
                combined = "\n---\n".join(r.answer for r in results)
                return RunResult(
                    answer=combined,
                    steps=sum(r.steps for r in results),
                    mode=config.mode,
                    events=[e for r in results for e in r.events],
                )

            raise ValueError(f"Unknown execution mode: {config.mode!r}")

        except Exception as exc:
            return RunResult(
                answer="",
                steps=0,
                mode=config.mode,
                ok=False,
                error=str(exc),
            )

    # ── Convenience wrappers ──────────────────────────────────────────────────

    async def run_browser_cua(
        self,
        task: str,
        max_steps: int = 50,
        stealth: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 800,
    ) -> RunResult:
        """
        Kernel cloud browser + Northstar manual CUA loop.

        Use this when:
        - The task is web-based and you have precise coordinates or
          annotated screenshots to guide the agent.
        - You need to integrate images/annotations from the recorded flow.
        - You want the tightest control over each step.

        The live_view_url is surfaced so the user can watch in real time.
        """
        return await self._run_browser_cua(RunConfig(
            mode=ExecutionMode.BROWSER_CUA,
            task=task,
            max_steps=max_steps,
            stealth=stealth,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        ))

    async def run_desktop_task(
        self,
        task: str,
        max_steps: int = 50,
        environment_id: str | None = None,
        persistent: bool = False,
    ) -> RunResult:
        """
        Lightcone autonomous desktop task.

        Use this when:
        - The task involves native desktop apps (Excel, SAP, ERP, legacy software).
        - You need multi-window or multi-application workflows.
        - You have an existing environment (environment_id) with apps pre-installed.

        Set persistent=True and save result.environment_id to reuse across runs.
        """
        return await self._run_lightcone_task(RunConfig(
            mode=ExecutionMode.DESKTOP_TASK,
            task=task,
            max_steps=max_steps,
            environment_id=environment_id,
            persistent=persistent,
        ), kind="desktop")

    async def run_browser_task(
        self,
        task: str,
        max_steps: int = 50,
        environment_id: str | None = None,
    ) -> RunResult:
        """
        Lightcone autonomous browser task.

        Use this when:
        - The task is web-only and you want full Northstar autonomy (no manual loop).
        - You want to chain multiple pages/sites in one instruction.
        """
        return await self._run_lightcone_task(RunConfig(
            mode=ExecutionMode.BROWSER_TASK,
            task=task,
            max_steps=max_steps,
            environment_id=environment_id,
        ), kind="browser")

    async def run_batch(
        self,
        records: list[dict],
        instruction_template: str,
        mode: ExecutionMode = ExecutionMode.DESKTOP_TASK,
        max_steps: int = 30,
        environment_id: str | None = None,
        concurrency: int = 1,
    ) -> list[RunResult]:
        """
        Run the same task template for each record.

        instruction_template uses Python str.format(**record):
            "Go to CRM. Create contact {name} with email {email} in company {company}."

        concurrency=1 (default) processes records one at a time.
        concurrency>1 runs multiple in parallel — use carefully.

        Returns one RunResult per record in the same order as records.
        """
        kind = "browser" if mode == ExecutionMode.BROWSER_TASK else "desktop"

        if concurrency == 1:
            results = []
            for i, record in enumerate(records):
                print(f"[batch {i+1}/{len(records)}] {record}")
                result = await self._run_lightcone_task(RunConfig(
                    mode=mode,
                    task=instruction_template.format(**record),
                    max_steps=max_steps,
                    environment_id=environment_id,
                ), kind=kind)
                results.append(result)
            return results

        sem = asyncio.Semaphore(concurrency)

        async def _one(i: int, record: dict) -> RunResult:
            async with sem:
                print(f"[batch {i+1}/{len(records)}] {record}")
                return await self._run_lightcone_task(RunConfig(
                    mode=mode,
                    task=instruction_template.format(**record),
                    max_steps=max_steps,
                    environment_id=environment_id,
                ), kind=kind)

        return list(await asyncio.gather(*[_one(i, r) for i, r in enumerate(records)]))

    # ── SOP entry point ───────────────────────────────────────────────────────

    async def execute_sop(
        self,
        sop: SOP,
        step_by_step: bool = False,
    ) -> RunResult:
        """
        Execute a compiled SOP.

        This is the primary backend entry point after the compiler (Claude) has
        turned a recording into a structured plan.

        Parameters
        ----------
        sop           The compiled SOP from the compiler.
        step_by_step  If True and surface=BROWSER, use the Kernel+Northstar CUA
                      loop with per-step visual grounding (each step sends its
                      reference screenshot alongside the instruction).
                      If False (default), flatten the SOP into one task prompt
                      and run it end-to-end with the autonomous Task API.

        Surface routing
        ---------------
        sop.surface == BROWSER  →  BROWSER_CUA (step_by_step=True)
                                   or BROWSER_TASK (step_by_step=False)
        sop.surface == DESKTOP  →  DESKTOP_TASK (always autonomous)

        The mode choice:
        - Use step_by_step=True when you have reference screenshots / annotations
          and want the model to visually locate each element.
        - Use step_by_step=False (default) for a simpler, more robust run where
          Northstar figures out the whole flow from the NL description.
        """
        if sop.surface == Surface.DESKTOP:
            return await self.run_desktop_task(
                task=sop.to_task_prompt(),
                max_steps=max(50, len(sop.steps) * 3),
                environment_id=sop.environment_id,
                persistent=sop.environment_id is not None,
            )

        # Browser surface
        if step_by_step:
            return await self._run_sop_step_by_step(sop)

        # One-shot autonomous browser task
        task = sop.to_task_prompt()
        if sop.start_url:
            return await self.run_browser_cua(
                task=task,
                max_steps=max(50, len(sop.steps) * 4),
            )
        return await self.run_browser_task(
            task=task,
            max_steps=max(50, len(sop.steps) * 3),
            environment_id=sop.environment_id,
        )

    async def _run_sop_step_by_step(self, sop: SOP) -> RunResult:
        """
        Kernel browser + Northstar, one Northstar call per SOP step.

        Each step sends:
          - The step instruction (intent + action detail)
          - The current live screenshot
          - The reference screenshot from the recording (if available)

        This gives Northstar visual grounding so it can find elements even
        when coordinates have shifted between recording and replay.
        """
        from kernel import AsyncKernel
        from tzafon import AsyncLightcone
        from app.infra.northstar_kernel import _capture, _computer_tool, _execute_action, _find_computer_call, _extract_text

        if not self._kernel_key:
            raise ValueError("KERNEL_API_KEY is required for step-by-step browser execution")
        if not self._lightcone_key:
            raise ValueError("TZAFON_API_KEY is required for step-by-step browser execution")

        kernel = AsyncKernel(api_key=self._kernel_key)
        lc = AsyncLightcone(api_key=self._lightcone_key)

        session = await kernel.browsers.create(
            stealth=True,
            viewport={"width": 1280, "height": 800},
        )
        sid = session.session_id
        live_url: str = getattr(session, "browser_live_view_url", "") or ""
        print(f"[kernel] browser {sid} (live: {live_url})")

        total_steps = 0
        all_events: list[Any] = []
        answer = ""
        step_prompts = sop.to_step_prompts()

        try:
            # Navigate to start URL if provided
            if sop.start_url:
                await kernel.browsers.playwright.execute(
                    sid,
                    code=f"await page.goto({sop.start_url!r}); await page.waitForLoadState('networkidle');",
                )
                await asyncio.sleep(1.0)

            for step_i, (step, prompt) in enumerate(zip(sop.steps, step_prompts)):
                print(f"\n[sop step {step_i + 1}/{len(sop.steps)}] {step.intent}")

                live_b64 = await _capture(kernel, sid)

                # Build input: instruction + live screenshot + optional reference screenshot
                content: list[dict] = [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{live_b64}",
                        "detail": "auto",
                    },
                ]
                if step.screenshot_b64:
                    content.append({
                        "type": "input_text",
                        "text": "Reference screenshot from the original recording (use this to identify the target element):",
                    })
                    content.append({
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{step.screenshot_b64}",
                        "detail": "auto",
                    })

                response = await lc.responses.create(
                    model="tzafon.northstar-cua-fast",
                    input=[{"role": "user", "content": content}],
                    tools=[_computer_tool(1280, 800)],
                )

                # Inner CUA loop for this step (max 10 actions per step)
                for _ in range(10):
                    cc = _find_computer_call(response)
                    if not cc:
                        break
                    action = cc.action
                    action_type = getattr(action, "type", "")
                    total_steps += 1
                    all_events.append({"sop_step": step_i + 1, "action": action_type})

                    if action_type in ("terminate", "done", "answer"):
                        answer = (
                            getattr(action, "text", "")
                            or getattr(action, "answer", "")
                            or _extract_text(response)
                        )
                        break

                    await _execute_action(kernel, sid, action)
                    await asyncio.sleep(1.0)

                    new_b64 = await _capture(kernel, sid)
                    response = await lc.responses.create(
                        model="tzafon.northstar-cua-fast",
                        previous_response_id=response.id,
                        input=[{
                            "type": "computer_call_output",
                            "call_id": cc.call_id,
                            "output": {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{new_b64}",
                                "detail": "auto",
                            },
                        }],
                        tools=[_computer_tool(1280, 800)],
                    )

                if step.wait_ms:
                    await asyncio.sleep(step.wait_ms / 1000)

            if not answer:
                answer = _extract_text(response)

        finally:
            try:
                await kernel.browsers.delete_by_id(sid)
            except Exception:
                pass

        return RunResult(
            answer=answer,
            steps=total_steps,
            mode=ExecutionMode.BROWSER_CUA,
            live_view_url=live_url or None,
            events=all_events,
        )

    # ── Internal executors ────────────────────────────────────────────────────

    async def _run_browser_cua(self, config: RunConfig) -> RunResult:
        """Kernel + Northstar manual loop."""
        from app.infra.northstar_kernel import NorthstarKernelAgent

        if not self._kernel_key:
            raise ValueError("KERNEL_API_KEY is required for BROWSER_CUA mode")
        if not self._lightcone_key:
            raise ValueError("TZAFON_API_KEY is required for BROWSER_CUA mode")

        agent = NorthstarKernelAgent(
            kernel_api_key=self._kernel_key,
            lightcone_api_key=self._lightcone_key,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
        )

        # Temporarily capture the live_view_url printed by the agent
        live_url: str | None = None
        _orig_print = __builtins__["print"] if isinstance(__builtins__, dict) else print

        import builtins
        _real_print = builtins.print

        def _intercept(*args, **kwargs):
            text = " ".join(str(a) for a in args)
            nonlocal live_url
            if "live:" in text and live_url is None:
                # "[kernel] browser <id> (live: <url>)"
                start = text.find("(live: ") + 7
                end = text.find(")", start)
                if start > 7 and end > start:
                    live_url = text[start:end]
            _real_print(*args, **kwargs)

        builtins.print = _intercept
        try:
            agent_result = await agent.run(
                task=config.task,
                max_steps=config.max_steps,
                stealth=config.stealth,
            )
        finally:
            builtins.print = _real_print

        return RunResult(
            answer=agent_result.answer,
            steps=agent_result.steps,
            mode=config.mode,
            live_view_url=live_url,
            events=agent_result.events,
        )

    async def _run_lightcone_task(
        self,
        config: RunConfig,
        kind: str,
    ) -> RunResult:
        """Lightcone autonomous Task API."""
        from app.infra.lightcone import LightconeClient

        if not self._lightcone_key:
            raise ValueError("TZAFON_API_KEY is required for DESKTOP_TASK / BROWSER_TASK mode")

        client = LightconeClient(api_key=self._lightcone_key)
        live_url: str | None = None
        env_id: str | None = config.environment_id

        if config.persistent and not env_id:
            # Create a fresh persistent environment; caller saves the id for next run
            sess = await client.create_persistent_computer(kind=kind)
            live_url = sess.live_view_url
            env_id = sess.id
            await sess.delete()

        elif env_id:
            # Peek at the live view URL if we can (best-effort)
            try:
                sess = await client.create_computer(
                    kind=kind,
                    persistent=True,
                    environment_id=env_id,
                )
                live_url = sess.live_view_url
                await sess.delete()
            except Exception:
                pass

        agent_result = await client.run_task_collect(
            instruction=config.task,
            kind=kind,
            max_steps=config.max_steps,
            environment_id=env_id,
            verbose=True,
        )

        return RunResult(
            answer=agent_result.answer,
            steps=agent_result.steps,
            mode=config.mode,
            live_view_url=live_url,
            environment_id=env_id,
            events=agent_result.events,
        )
