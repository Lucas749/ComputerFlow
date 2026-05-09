"""
Live integration test: browser → Hacker News first article summary.

Target:   KERNEL_BROWSER
Strategy: CUA_LOOP

Uses start_url to pre-navigate via Playwright, then a single CUA step
with the full task so Northstar has one conversation to finish it.

Run:
    PYTHONPATH=backend python scripts/test_browser_hn.py
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
    title="HN first article summary",
    goal="Return a 3-sentence summary of the #1 article on Hacker News.",
    # start_url → Playwright pre-navigates before the CUA loop starts,
    # so Northstar's first screenshot is already the loaded HN front page.
    start_url="https://news.ycombinator.com",
    steps=[
        SOPStep(
            intent=(
                "You are on Hacker News (news.ycombinator.com). "
                "Identify the #1 ranked story — the very first article link at the top of the list. "
                "Click its title to open the article page. "
                "Wait for the page to load, then read the content. "
                "Write a clear 3-sentence summary of what the article is about."
            ),
            action=ActionType.CLICK,
            surface=Surface.BROWSER,
            target=RunTarget.KERNEL_BROWSER,
            target_kind=TargetKind.DESCRIPTION,
            description="The first story title link at the top of the Hacker News front page",
        ),
    ],
    default_target=RunTarget.KERNEL_BROWSER,
    default_strategy=ExecutionStrategy.CUA_LOOP,
    options=RunOptions(
        viewport_width=1280,
        viewport_height=720,
        stealth=True,
        step_delay_ms=1500,
        max_actions_per_step=50,
    ),
)


async def main() -> None:
    runner = ComputerFlowRunner(open_live_views=True)
    print("=" * 70)
    print("TEST: browser → Hacker News first article summary")
    print("=" * 70)

    result = await runner.run_flow(FLOW)

    live = result.live_view_urls.get("kernel_browser")
    if live:
        print(f"\nLive view: {live}")

    print(f"\nSteps taken: {result.steps_taken}")
    print(f"OK:          {result.ok}")
    if result.replay_id:
        print(f"Replay ID:   {result.replay_id}")
    if result.error:
        print(f"Error:       {result.error}")
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(result.answer or "(no answer returned)")
    assert result.ok, f"Flow failed: {result.error}"
    assert result.answer, "Expected a non-empty answer"
    print("\n✓ PASS")


if __name__ == "__main__":
    asyncio.run(main())
