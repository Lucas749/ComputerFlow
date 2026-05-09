"""
Kernel infrastructure client.

Wraps the `kernel` Python SDK to provide:
  - Browser session lifecycle (create, delete)
  - Playwright code execution against live Kernel browsers
  - Computer controls (screenshot, mouse, keyboard) for vision-based flows
  - CDP / WebDriver BiDi connection URLs for direct framework integration
  - Live-view URL for streaming the session into the PiP monitor

Usage
-----
Context manager (auto-cleanup):

    with KernelClient().browser() as sess:
        sess.playwright("await page.goto('https://example.com')")
        img = sess.screenshot()

Explicit lifecycle:

    client = KernelClient()
    sess = client.create_browser()
    try:
        result = sess.playwright("await page.click('button#submit')")
    finally:
        sess.delete()

Direct CDPsession (use with Playwright Python):

    sess = client.create_browser()
    # Connect your own Playwright instance:
    #   browser = await playwright.chromium.connect_over_cdp(sess.cdp_ws_url)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class PlaywrightResult:
    """Return value of BrowserSession.playwright()."""
    raw: Any
    output: Any = None          # Return value from the executed code (if any)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ComputerScreenshot:
    """Return value of BrowserSession.screenshot()."""
    raw: Any
    b64: str | None = None      # base64 PNG
    url: str | None = None      # pre-signed URL if the SDK provides one


@dataclass
class BrowserInfo:
    """Immutable metadata about a live Kernel browser session."""
    session_id: str
    cdp_ws_url: str | None
    webdriver_ws_url: str | None
    live_view_url: str | None
    raw: Any = field(default=None, repr=False)


# ── BrowserSession ─────────────────────────────────────────────────────────────

class BrowserSession:
    """
    Wrapper around a live Kernel browser session.
    Exposes Playwright execution, computer controls, and connection URLs.
    """

    def __init__(self, browser, sdk: Kernel) -> None:
        self._browser = browser
        self._sdk = sdk

    @property
    def session_id(self) -> str:
        return self._browser.session_id

    @property
    def cdp_ws_url(self) -> str | None:
        return getattr(self._browser, "cdp_ws_url", None)

    @property
    def webdriver_ws_url(self) -> str | None:
        return getattr(self._browser, "webdriver_ws_url", None)

    @property
    def live_view_url(self) -> str | None:
        """URL for the noVNC / live-view stream (used by the PiP monitor)."""
        return getattr(self._browser, "live_view_url", None)

    @property
    def info(self) -> BrowserInfo:
        return BrowserInfo(
            session_id=self.session_id,
            cdp_ws_url=self.cdp_ws_url,
            webdriver_ws_url=self.webdriver_ws_url,
            live_view_url=self.live_view_url,
            raw=self._browser,
        )

    # ── Playwright ────────────────────────────────────────────────────────────

    def playwright(self, code: str) -> PlaywrightResult:
        """
        Execute arbitrary Playwright code in Kernel's managed context.

        The code runs as an async function body. `page` is already available.
        Return values are forwarded through `result.output`.

        Example:
            sess.playwright("await page.goto('https://example.com')")
            result = sess.playwright("return await page.title()")
            print(result.output)  # "Example Domain"
        """
        raw = self._sdk.browsers.playwright.execute(
            id=self.session_id,
            code=code,
        )
        error = getattr(raw, "error", None) or getattr(raw, "error_message", None)
        output = getattr(raw, "result", None) or getattr(raw, "output", None)
        return PlaywrightResult(raw=raw, output=output, error=str(error) if error else None)

    def goto(self, url: str) -> PlaywrightResult:
        """Navigate to URL."""
        return self.playwright(f"await page.goto({url!r})")

    def click(self, selector: str) -> PlaywrightResult:
        """Click a CSS selector."""
        return self.playwright(f"await page.click({selector!r})")

    def fill(self, selector: str, value: str) -> PlaywrightResult:
        """Fill an input field."""
        safe_value = value.replace("'", "\\'")
        return self.playwright(f"await page.fill({selector!r}, '{safe_value}')")

    def type_into(self, selector: str, text: str) -> PlaywrightResult:
        """Type text into an element (key-by-key, triggers keyboard events)."""
        safe = text.replace("'", "\\'")
        return self.playwright(f"await page.type({selector!r}, '{safe}')")

    def press(self, selector: str, key: str) -> PlaywrightResult:
        """Press a key while an element is focused."""
        return self.playwright(f"await page.press({selector!r}, {key!r})")

    def wait_for_selector(self, selector: str, timeout_ms: int = 5000) -> PlaywrightResult:
        return self.playwright(
            f"await page.waitForSelector({selector!r}, {{timeout: {timeout_ms}}})"
        )

    def wait_for_url(self, url_pattern: str, timeout_ms: int = 10000) -> PlaywrightResult:
        return self.playwright(
            f"await page.waitForURL({url_pattern!r}, {{timeout: {timeout_ms}}})"
        )

    def extract_text(self, selector: str) -> PlaywrightResult:
        """Return the inner text of an element."""
        return self.playwright(f"return await page.innerText({selector!r})")

    def extract_all(self, selector: str, attribute: str = "innerText") -> PlaywrightResult:
        """Return a list of values for all matching elements."""
        if attribute == "innerText":
            code = (
                f"const els = await page.$$('{selector}');"
                "return await Promise.all(els.map(el => el.innerText()));"
            )
        else:
            code = (
                f"const els = await page.$$('{selector}');"
                f"return await Promise.all(els.map(el => el.getAttribute('{attribute}')));"
            )
        return self.playwright(code)

    def evaluate(self, js_expression: str) -> PlaywrightResult:
        """Evaluate a JS expression in the page context and return the result."""
        return self.playwright(f"return await page.evaluate(`{js_expression}`)")

    def scroll_to_bottom(self) -> PlaywrightResult:
        return self.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    # ── Computer controls ─────────────────────────────────────────────────────

    def screenshot(self) -> ComputerScreenshot:
        """Capture a screenshot of the current browser viewport."""
        try:
            raw = self._sdk.browsers.screenshot(id=self.session_id)
        except AttributeError:
            # Fallback: some SDK versions expose it on the computer controls path
            raw = self._sdk.browsers.computer.screenshot(id=self.session_id)

        b64 = getattr(raw, "image", None) or getattr(raw, "data", None)
        url = getattr(raw, "url", None)
        if b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        return ComputerScreenshot(raw=raw, b64=b64, url=url)

    def mouse_click(self, x: int, y: int, button: str = "left") -> None:
        """Direct mouse click at pixel coordinates (computer controls path)."""
        self._sdk.browsers.computer.click(id=self.session_id, x=x, y=y, button=button)

    def mouse_move(self, x: int, y: int) -> None:
        self._sdk.browsers.computer.move(id=self.session_id, x=x, y=y)

    def keyboard_type(self, text: str) -> None:
        """Type text via computer controls (bypasses the DOM, fires OS-level events)."""
        self._sdk.browsers.computer.type(id=self.session_id, text=text)

    def keyboard_press(self, key: str) -> None:
        """Press a key via computer controls. E.g. "Enter", "Tab", "Escape"."""
        self._sdk.browsers.computer.key(id=self.session_id, key=key)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def delete(self) -> None:
        try:
            self._sdk.browsers.delete(id=self.session_id)
        except Exception:
            pass

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *_) -> None:
        self.delete()


# ── KernelClient ───────────────────────────────────────────────────────────────

class KernelClient:
    """
    Top-level client for all Kernel browser-automation operations.

    Reads KERNEL_API_KEY from the environment; override by passing api_key.
    """

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("KERNEL_API_KEY")
        if not key:
            raise ValueError(
                "KERNEL_API_KEY not set. "
                "Pass api_key= or set the environment variable."
            )
        from kernel import Kernel  # deferred so tests can stub sys.modules first
        self._sdk = Kernel(api_key=key)

    # ── Browsers ──────────────────────────────────────────────────────────────

    def create_browser(self, stealth: bool = False, gpu: bool = False) -> BrowserSession:
        """
        Provision a new Kernel browser session.

        stealth: enable bot-detection bypass (residential proxy + fingerprint spoofing)
        gpu:     enable GPU acceleration (for WebGL-heavy pages)
        """
        kwargs: dict = {}
        if stealth:
            kwargs["stealth"] = True
        if gpu:
            kwargs["gpu"] = True
        browser = self._sdk.browsers.create(**kwargs)
        return BrowserSession(browser=browser, sdk=self._sdk)

    @contextmanager
    def browser(
        self,
        stealth: bool = False,
        gpu: bool = False,
    ) -> Generator[BrowserSession, None, None]:
        """
        Context manager that creates and automatically deletes a browser session.

            with client.browser() as sess:
                sess.goto("https://example.com")
                result = sess.extract_text("h1")
        """
        sess = self.create_browser(stealth=stealth, gpu=gpu)
        try:
            yield sess
        finally:
            sess.delete()

    def list_browsers(self) -> list[BrowserInfo]:
        """Return all active browser sessions for this account."""
        try:
            raw_list = self._sdk.browsers.list()
        except Exception:
            return []
        sessions = []
        for item in raw_list if isinstance(raw_list, list) else []:
            sessions.append(BrowserInfo(
                session_id=getattr(item, "session_id", ""),
                cdp_ws_url=getattr(item, "cdp_ws_url", None),
                webdriver_ws_url=getattr(item, "webdriver_ws_url", None),
                live_view_url=getattr(item, "live_view_url", None),
                raw=item,
            ))
        return sessions
