"""
Unit tests for backend/app/infra/kernel.py.

All Kernel SDK calls are mocked — no network, no API key required.
"""

import sys
import os
import types
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


# ── Minimal kernel stub ───────────────────────────────────────────────────────

def _make_kernel_stub():
    mod = types.ModuleType("kernel")

    class Kernel:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.browsers = MagicMock()

    mod.Kernel = Kernel
    return mod


kernel_stub = _make_kernel_stub()
sys.modules.setdefault("kernel", kernel_stub)

from app.infra.kernel import (  # noqa: E402
    KernelClient,
    BrowserSession,
    BrowserInfo,
    PlaywrightResult,
    ComputerScreenshot,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    return sdk


@pytest.fixture
def mock_browser():
    b = MagicMock()
    b.session_id = "sess_abc"
    b.cdp_ws_url = "ws://kernel.internal/cdp/sess_abc"
    b.webdriver_ws_url = "ws://kernel.internal/bidi/sess_abc"
    b.live_view_url = "https://live.kernel.sh/view/sess_abc"
    return b


@pytest.fixture
def session(mock_browser, mock_sdk):
    return BrowserSession(browser=mock_browser, sdk=mock_sdk)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KERNEL_API_KEY", "sk_test_kernel")
    c = KernelClient()
    c._sdk = MagicMock()
    yield c


# ── KernelClient construction ─────────────────────────────────────────────────

def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("KERNEL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="KERNEL_API_KEY"):
        KernelClient()


def test_client_accepts_explicit_key():
    c = KernelClient(api_key="sk_explicit")
    assert c._sdk.api_key == "sk_explicit"


def test_client_reads_env_key(monkeypatch):
    monkeypatch.setenv("KERNEL_API_KEY", "sk_env")
    c = KernelClient()
    assert c._sdk.api_key == "sk_env"


# ── create_browser ────────────────────────────────────────────────────────────

def test_create_browser_default(client):
    fake = MagicMock()
    fake.session_id = "sess_1"
    client._sdk.browsers.create.return_value = fake

    sess = client.create_browser()

    client._sdk.browsers.create.assert_called_once_with()
    assert isinstance(sess, BrowserSession)
    assert sess.session_id == "sess_1"


def test_create_browser_stealth(client):
    fake = MagicMock()
    fake.session_id = "sess_s"
    client._sdk.browsers.create.return_value = fake

    client.create_browser(stealth=True)
    client._sdk.browsers.create.assert_called_once_with(stealth=True)


def test_create_browser_gpu(client):
    fake = MagicMock()
    fake.session_id = "sess_g"
    client._sdk.browsers.create.return_value = fake

    client.create_browser(gpu=True)
    client._sdk.browsers.create.assert_called_once_with(gpu=True)


# ── context manager ───────────────────────────────────────────────────────────

def test_browser_context_manager_cleanup(client):
    fake = MagicMock()
    fake.session_id = "sess_ctx"
    client._sdk.browsers.create.return_value = fake

    with client.browser() as sess:
        assert sess.session_id == "sess_ctx"

    client._sdk.browsers.delete.assert_called_once_with(id="sess_ctx")


def test_browser_context_manager_cleanup_on_error(client):
    fake = MagicMock()
    fake.session_id = "sess_err"
    client._sdk.browsers.create.return_value = fake

    with pytest.raises(ValueError):
        with client.browser() as sess:
            raise ValueError("boom")

    client._sdk.browsers.delete.assert_called_once_with(id="sess_err")


# ── BrowserSession properties ─────────────────────────────────────────────────

def test_session_id(session):
    assert session.session_id == "sess_abc"


def test_session_cdp_url(session):
    assert "cdp" in session.cdp_ws_url


def test_session_live_view_url(session):
    assert session.live_view_url.startswith("https://")


def test_session_info(session):
    info = session.info
    assert isinstance(info, BrowserInfo)
    assert info.session_id == "sess_abc"
    assert info.cdp_ws_url is not None


# ── Playwright execution ──────────────────────────────────────────────────────

def test_playwright_success(session, mock_sdk):
    raw = MagicMock()
    raw.error = None
    raw.error_message = None
    raw.result = "Example Domain"
    mock_sdk.browsers.playwright.execute.return_value = raw

    result = session.playwright("return await page.title()")

    assert isinstance(result, PlaywrightResult)
    assert result.ok
    assert result.output == "Example Domain"
    mock_sdk.browsers.playwright.execute.assert_called_once_with(
        id="sess_abc", code="return await page.title()"
    )


def test_playwright_error(session, mock_sdk):
    raw = MagicMock()
    raw.error = "TimeoutError: waiting for selector"
    raw.result = None
    mock_sdk.browsers.playwright.execute.return_value = raw

    result = session.playwright("await page.click('#missing')")
    assert not result.ok
    assert "TimeoutError" in result.error


def test_goto(session, mock_sdk):
    raw = MagicMock()
    raw.error = None
    raw.result = None
    mock_sdk.browsers.playwright.execute.return_value = raw

    session.goto("https://example.com")
    call_kwargs = mock_sdk.browsers.playwright.execute.call_args.kwargs
    assert "page.goto" in call_kwargs["code"]
    assert "https://example.com" in call_kwargs["code"]


def test_click(session, mock_sdk):
    raw = MagicMock()
    raw.error = None
    raw.result = None
    mock_sdk.browsers.playwright.execute.return_value = raw

    session.click("button#submit")
    code = mock_sdk.browsers.playwright.execute.call_args.kwargs["code"]
    assert "page.click" in code
    assert "button#submit" in code


def test_fill(session, mock_sdk):
    raw = MagicMock()
    raw.error = None
    raw.result = None
    mock_sdk.browsers.playwright.execute.return_value = raw

    session.fill("input[name='email']", "user@example.com")
    code = mock_sdk.browsers.playwright.execute.call_args.kwargs["code"]
    assert "page.fill" in code
    assert "user@example.com" in code


def test_fill_escapes_single_quotes(session, mock_sdk):
    raw = MagicMock()
    raw.error = None
    raw.result = None
    mock_sdk.browsers.playwright.execute.return_value = raw

    session.fill("input", "it's a test")
    code = mock_sdk.browsers.playwright.execute.call_args.kwargs["code"]
    assert "it\\'s a test" in code


def test_extract_text(session, mock_sdk):
    raw = MagicMock()
    raw.error = None
    raw.result = "Welcome!"
    mock_sdk.browsers.playwright.execute.return_value = raw

    result = session.extract_text("h1")
    assert result.output == "Welcome!"
    code = mock_sdk.browsers.playwright.execute.call_args.kwargs["code"]
    assert "innerText" in code


def test_evaluate(session, mock_sdk):
    raw = MagicMock()
    raw.error = None
    raw.result = 42
    mock_sdk.browsers.playwright.execute.return_value = raw

    result = session.evaluate("document.querySelectorAll('li').length")
    assert result.output == 42


# ── Screenshots ───────────────────────────────────────────────────────────────

def test_screenshot(session, mock_sdk):
    raw = MagicMock()
    raw.image = "iVBORw0KGgo="
    raw.url = None
    mock_sdk.browsers.screenshot.return_value = raw

    result = session.screenshot()

    assert isinstance(result, ComputerScreenshot)
    assert result.b64 == "iVBORw0KGgo="
    mock_sdk.browsers.screenshot.assert_called_once_with(id="sess_abc")


def test_screenshot_strips_data_uri(session, mock_sdk):
    raw = MagicMock()
    raw.image = "data:image/png;base64,iVBORw0KGgo="
    raw.url = None
    mock_sdk.browsers.screenshot.return_value = raw

    result = session.screenshot()
    assert result.b64 == "iVBORw0KGgo="


# ── Computer controls ─────────────────────────────────────────────────────────

def test_mouse_click(session, mock_sdk):
    session.mouse_click(200, 300)
    mock_sdk.browsers.computer.click.assert_called_once_with(
        id="sess_abc", x=200, y=300, button="left"
    )


def test_keyboard_type(session, mock_sdk):
    session.keyboard_type("hello")
    mock_sdk.browsers.computer.type.assert_called_once_with(id="sess_abc", text="hello")


def test_keyboard_press(session, mock_sdk):
    session.keyboard_press("Enter")
    mock_sdk.browsers.computer.key.assert_called_once_with(id="sess_abc", key="Enter")


# ── Session delete ────────────────────────────────────────────────────────────

def test_delete(session, mock_sdk):
    session.delete()
    mock_sdk.browsers.delete.assert_called_once_with(id="sess_abc")


def test_delete_swallows_error(session, mock_sdk):
    mock_sdk.browsers.delete.side_effect = Exception("gone")
    session.delete()  # must not raise


def test_context_manager(mock_browser, mock_sdk):
    sess = BrowserSession(browser=mock_browser, sdk=mock_sdk)
    with sess as s:
        assert s is sess
    mock_sdk.browsers.delete.assert_called_once_with(id="sess_abc")


# ── list_browsers ─────────────────────────────────────────────────────────────

def test_list_browsers(client):
    b1 = MagicMock()
    b1.session_id = "s1"
    b1.cdp_ws_url = "ws://x/s1"
    b1.webdriver_ws_url = None
    b1.live_view_url = "https://live/s1"
    client._sdk.browsers.list.return_value = [b1]

    infos = client.list_browsers()
    assert len(infos) == 1
    assert infos[0].session_id == "s1"


def test_list_browsers_handles_exception(client):
    client._sdk.browsers.list.side_effect = Exception("network error")
    infos = client.list_browsers()
    assert infos == []
