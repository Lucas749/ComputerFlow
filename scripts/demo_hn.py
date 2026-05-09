"""
Demo: Kernel browser + Lightcone Northstar → Hacker News first article summary.

The browser is a CLOUD browser — Kernel runs it remotely.
When you run this script it will print a live-view URL.
Open that URL in your browser to watch the agent work in real time.

Run from the project root:
    PYTHONPATH=backend python scripts/demo_hn.py

Requires .env with:
    KERNEL_API_KEY=...
    TZAFON_API_KEY=...   (or LIGHTCONE_API_KEY=...)
"""

import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from kernel import AsyncKernel
from tzafon import AsyncLightcone
from app.infra.northstar_kernel import (
    _capture, _computer_tool, _execute_action,
    _find_computer_call, _extract_text,
)

# Task starts after we've already landed on HN — Northstar just needs to
# identify the top article, click it, and summarize.
TASK = (
    "You are on Hacker News (news.ycombinator.com). "
    "Identify the #1 ranked story (the first article link at the top of the list). "
    "Click on its title to open the article in the browser. "
    "Wait for the page to load, then read the content. "
    "Write a clear 3-sentence summary of what the article is about."
)


async def main() -> None:
    kernel = AsyncKernel(api_key=os.environ["KERNEL_API_KEY"])
    lc = AsyncLightcone(
        api_key=os.environ.get("TZAFON_API_KEY") or os.environ["LIGHTCONE_API_KEY"]
    )

    session = await kernel.browsers.create(
        stealth=True,
        viewport={"width": 1280, "height": 800},
    )
    sid = session.session_id

    live_url = session.browser_live_view_url
    print("=" * 70)
    print(f"  Live view (open this in your browser to watch):")
    print(f"  {live_url}")
    print("=" * 70)

    # Open live view automatically in the default browser
    subprocess.Popen(["open", live_url])

    try:
        # Pre-navigate to HN via Playwright so Northstar starts on the right page
        print("[playwright] navigating to news.ycombinator.com ...")
        await kernel.browsers.playwright.execute(
            sid,
            code="await page.goto('https://news.ycombinator.com'); await page.waitForLoadState('networkidle');",
        )
        await asyncio.sleep(1.5)
        print("[playwright] page loaded")

        b64 = await _capture(kernel, sid)

        response = await lc.responses.create(
            model="tzafon.northstar-cua-fast",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": TASK},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64}",
                        "detail": "auto",
                    },
                ],
            }],
            tools=[_computer_tool(1280, 800)],
        )

        answer = ""
        for step in range(1, 40):
            cc = _find_computer_call(response)

            if not cc:
                answer = _extract_text(response)
                print(f"\n[step {step}] Northstar finished.")
                break

            action = cc.action
            action_type = getattr(action, "type", "?")

            detail = ""
            if hasattr(action, "x"):
                detail = f" ({action.x}, {action.y})"
            if hasattr(action, "text") and action.text:
                detail = f" {repr(str(action.text)[:50])}"
            if hasattr(action, "url"):
                detail = f" {action.url}"
            print(f"  step {step:>2}: {action_type}{detail}")

            if action_type in ("terminate", "done", "answer"):
                answer = (
                    getattr(action, "text", "")
                    or getattr(action, "answer", "")
                    or _extract_text(response)
                )
                break

            await _execute_action(kernel, sid, action)
            await asyncio.sleep(1.5)

            b64 = await _capture(kernel, sid)
            response = await lc.responses.create(
                model="tzafon.northstar-cua-fast",
                previous_response_id=response.id,
                input=[{
                    "type": "computer_call_output",
                    "call_id": cc.call_id,
                    "output": {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64}",
                        "detail": "auto",
                    },
                }],
                tools=[_computer_tool(1280, 800)],
            )

        print("\n" + "=" * 70)
        print("ARTICLE SUMMARY")
        print("=" * 70)
        print(answer or "(no summary returned — check the live view URL above)")

    finally:
        await kernel.browsers.delete_by_id(sid)
        print(f"\n[kernel] session {sid} deleted")


if __name__ == "__main__":
    asyncio.run(main())
