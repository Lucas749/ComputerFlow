"""
Live integration test: browser + desktop handoff.

  Group 1 (KERNEL_BROWSER, CUA_LOOP):
    Navigate to Hacker News, read the #1 article title, remember it.

  Group 2 (LIGHTCONE_OS, CUA_LOOP):
    Open a text editor, type that title into it, and save.

This exercises the full handoff flow: two targets, two sessions, one run.
Both live-view URLs are printed so you can watch both surfaces simultaneously.

Run:
    PYTHONPATH=backend python scripts/test_mixed_hn_excel.py
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
    title="HN title → text editor (mixed handoff)",
    goal=(
        "Read the title of the #1 story on Hacker News, "
        "then type that exact title into a text editor on the desktop."
    ),
    steps=[
        # ── Group 1: browser ──────────────────────────────────────────────────
        SOPStep(
            intent=(
                "Go to https://news.ycombinator.com. "
                "Find the #1 ranked story — it is the very first article link at the top of the list. "
                "Read its title carefully. "
                "Do NOT click it. Just return the exact title text as your answer."
            ),
            action=ActionType.NAVIGATE,
            surface=Surface.BROWSER,
            target=RunTarget.KERNEL_BROWSER,
            target_kind=TargetKind.DESCRIPTION,
        ),
        # ── Group 2: desktop (handoff) ────────────────────────────────────────
        SOPStep(
            intent=(
                "Open a terminal. Run: mousepad &\n"
                "Wait for the Mousepad text editor to open. "
                "If mousepad is not available, try: gedit & or xed &\n"
                "Once a text editor is open, click in the text area. "
                "Type the Hacker News article title that was retrieved in the previous step. "
                "Save the file (Ctrl+S). "
                "The editor should now contain the article title."
            ),
            action=ActionType.TYPE,
            surface=Surface.DESKTOP,
            target=RunTarget.LIGHTCONE_OS,
            target_kind=TargetKind.DESCRIPTION,
        ),
    ],
    default_strategy=ExecutionStrategy.CUA_LOOP,
    options=RunOptions(
        viewport_width=1280,
        viewport_height=720,
        stealth=True,
        step_delay_ms=1500,
        max_actions_per_step=100,
        max_total_actions=300,
    ),
)


async def main() -> None:
    runner = ComputerFlowRunner(open_live_views=True)
    print("=" * 70)
    print("TEST: browser (HN title) + desktop handoff (text editor)")
    print("=" * 70)
    print(
        "\nNote: the browser step extracts the title; the desktop step types it.\n"
        "These run on separate cloud sessions — both live views will open.\n"
    )

    result = await runner.run_flow(FLOW)

    for key, url in result.live_view_urls.items():
        if url and not key.startswith("_"):
            print(f"\nLive view [{key}]: {url}")

    print(f"\nSteps taken: {result.steps_taken}")
    print(f"OK:          {result.ok}")
    if result.replay_id:
        print(f"Replay ID:   {result.replay_id}")
    if result.error:
        print(f"Error:       {result.error}")
    if result.environment_id:
        print(f"Env ID (save for reuse): {result.environment_id}")
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(result.answer or "(flow completed — check live views above)")
    assert result.ok, f"Flow failed: {result.error}"
    print("\n✓ PASS")


if __name__ == "__main__":
    asyncio.run(main())
