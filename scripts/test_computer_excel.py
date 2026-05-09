"""
Live integration test: Lightcone OS → LibreOffice Calc → type "Hello" in A1.

Target:   LIGHTCONE_OS
Strategy: CUA_LOOP (single step)

Run:
    PYTHONPATH=backend python scripts/test_computer_excel.py
"""

import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from app.infra.runner import ComputerFlowRunner
from app.infra.types import (
    ActionType, ExecutionStrategy, FlowRequest, RunOptions,
    RunTarget, SOPStep, Surface, TargetKind,
)


FLOW = FlowRequest(
    title="LibreOffice Calc — Hello in A1",
    goal="Open LibreOffice Calc, click cell A1, type 'Hello', press Enter.",
    steps=[
        SOPStep(
            intent=(
                "Open a terminal. Run: apt-get install -y libreoffice 2>/dev/null; libreoffice --calc &\n"
                "Wait for LibreOffice Calc to open. "
                "Click on cell A1 (the top-left cell in the spreadsheet). "
                "Type the word 'Hello'. "
                "Press Enter to confirm the entry. "
                "Confirm 'Hello' is now visible in cell A1."
            ),
            action=ActionType.TYPE,
            surface=Surface.DESKTOP,
            target=RunTarget.LIGHTCONE_OS,
            target_kind=TargetKind.DESCRIPTION,
            text="Hello",
        ),
    ],
    default_target=RunTarget.LIGHTCONE_OS,
    default_strategy=ExecutionStrategy.CUA_LOOP,
    options=RunOptions(
        viewport_width=1280,
        viewport_height=720,
        step_delay_ms=2000,
        max_actions_per_step=60,
        max_total_actions=120,
    ),
)


async def main() -> None:
    runner = ComputerFlowRunner(open_live_views=True)
    print("=" * 70)
    print("TEST: Lightcone OS → LibreOffice Calc → type Hello in A1")
    print("=" * 70)

    result = await runner.run_flow(FLOW)

    live = result.live_view_urls.get("lightcone_os")
    if live:
        print(f"\nLive view: {live}")

    print(f"\nSteps taken: {result.steps_taken}")
    print(f"OK:          {result.ok}")
    if result.error:
        print(f"Error:       {result.error}")
    if result.environment_id:
        print(f"Env ID (save for reuse): {result.environment_id}")
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(result.answer or "(flow completed — check live view)")
    assert result.ok, f"Flow failed: {result.error}"
    print("\n✓ PASS")


if __name__ == "__main__":
    asyncio.run(main())
