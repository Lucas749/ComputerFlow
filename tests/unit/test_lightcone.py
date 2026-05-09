"""
Unit tests for backend/app/infra/lightcone.py (async).

All Lightcone SDK calls are mocked — no network, no API key required.
"""

import sys
import os
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


# ── Minimal tzafon async stub ─────────────────────────────────────────────────

def _make_tzafon_stub():
    mod = types.ModuleType("tzafon")

    class AsyncLightcone:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.computers = MagicMock()
            self.computers.create = AsyncMock()
            self.computers.screenshot = AsyncMock()
            self.computers.navigate = AsyncMock()
            self.computers.click = AsyncMock()
            self.computers.double_click = AsyncMock()
            self.computers.right_click = AsyncMock()
            self.computers.scroll = AsyncMock()
            self.computers.drag = AsyncMock()
            self.computers.type = AsyncMock()
            self.computers.hotkey = AsyncMock()
            self.computers.key_down = AsyncMock()
            self.computers.key_up = AsyncMock()
            self.computers.mouse_down = AsyncMock()
            self.computers.mouse_up = AsyncMock()
            self.computers.html = AsyncMock()
            self.computers.viewport = AsyncMock()
            self.computers.keepalive = AsyncMock()
            self.computers.delete = AsyncMock()
            self.computers.batch = AsyncMock()
            self.computers.tabs = MagicMock()
            self.computers.tabs.list = AsyncMock()
            self.computers.exec = MagicMock()
            self.computers.exec.sync = AsyncMock()
            self.computers.exec.create = AsyncMock()
            self.agent = MagicMock()
            self.agent.tasks = MagicMock()
            self.agent.tasks.start = AsyncMock()
            self.agent.tasks.start_stream = AsyncMock()
            self.agent.tasks.retrieve_status = AsyncMock()
            self.agent.tasks.pause = AsyncMock()
            self.agent.tasks.resume = AsyncMock()
            self.agent.tasks.inject_message = AsyncMock()
            self.responses = MagicMock()
            self.responses.create = AsyncMock()

    mod.AsyncLightcone = AsyncLightcone
    return mod


tzafon_stub = _make_tzafon_stub()
sys.modules.setdefault("tzafon", tzafon_stub)

from app.infra.lightcone import (
    LightconeClient,
    ComputerSession,
    ScreenshotResult,
    ActionResult,
    ExecResult,
    TaskEvent,
    TaskHandle,
    AgentResult,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_raw_computer(cid="comp_abc", endpoints=None):
    raw = MagicMock()
    raw.id = cid
    raw.kind = "desktop"
    raw.status = "running"
    raw.endpoints = endpoints or {"debug": "/debug/abc", "screencast": "/screencast/abc"}
    return raw


def _make_action_raw(status="success"):
    raw = MagicMock()
    raw.status = status
    raw.result = None
    raw.page_context = None
    raw.error_message = None
    return raw


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    sdk.computers.screenshot = AsyncMock()
    sdk.computers.navigate = AsyncMock()
    sdk.computers.click = AsyncMock()
    sdk.computers.double_click = AsyncMock()
    sdk.computers.right_click = AsyncMock()
    sdk.computers.scroll = AsyncMock()
    sdk.computers.drag = AsyncMock()
    sdk.computers.type = AsyncMock()
    sdk.computers.hotkey = AsyncMock()
    sdk.computers.key_down = AsyncMock()
    sdk.computers.key_up = AsyncMock()
    sdk.computers.mouse_down = AsyncMock()
    sdk.computers.mouse_up = AsyncMock()
    sdk.computers.html = AsyncMock()
    sdk.computers.viewport = AsyncMock()
    sdk.computers.keepalive = AsyncMock()
    sdk.computers.delete = AsyncMock()
    sdk.computers.batch = AsyncMock()
    sdk.computers.tabs = MagicMock()
    sdk.computers.tabs.list = AsyncMock()
    sdk.computers.exec = MagicMock()
    sdk.computers.exec.sync = AsyncMock()
    sdk.computers.exec.create = AsyncMock()
    sdk.agent = MagicMock()
    sdk.agent.tasks = MagicMock()
    sdk.agent.tasks.start = AsyncMock()
    sdk.agent.tasks.start_stream = AsyncMock()
    sdk.agent.tasks.retrieve_status = AsyncMock()
    sdk.agent.tasks.pause = AsyncMock()
    sdk.agent.tasks.resume = AsyncMock()
    sdk.agent.tasks.inject_message = AsyncMock()
    sdk.responses = MagicMock()
    sdk.responses.create = AsyncMock()
    return sdk


@pytest.fixture
def raw_computer():
    return _make_raw_computer()


@pytest.fixture
def session(raw_computer, mock_sdk):
    return ComputerSession(raw=raw_computer, sdk=mock_sdk)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TZAFON_API_KEY", "sk_test_fake")
    c = LightconeClient()
    c._sdk = MagicMock()
    c._sdk.computers = MagicMock()
    c._sdk.computers.create = AsyncMock()
    c._sdk.computers.delete = AsyncMock()
    c._sdk.computers.exec = MagicMock()
    c._sdk.computers.exec.sync = AsyncMock()
    c._sdk.computers.exec.create = AsyncMock()
    c._sdk.computers.batch = AsyncMock()
    c._sdk.agent = MagicMock()
    c._sdk.agent.tasks = MagicMock()
    c._sdk.agent.tasks.start = AsyncMock()
    c._sdk.agent.tasks.start_stream = AsyncMock()
    c._sdk.agent.tasks.retrieve_status = AsyncMock()
    c._sdk.agent.tasks.pause = AsyncMock()
    c._sdk.agent.tasks.resume = AsyncMock()
    c._sdk.agent.tasks.inject_message = AsyncMock()
    c._sdk.responses = MagicMock()
    c._sdk.responses.create = AsyncMock()
    return c


# ── Construction ──────────────────────────────────────────────────────────────

def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("TZAFON_API_KEY", raising=False)
    monkeypatch.delenv("LIGHTCONE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TZAFON_API_KEY"):
        LightconeClient()


def test_client_accepts_explicit_key():
    c = LightconeClient(api_key="sk_explicit")
    assert c._sdk.api_key == "sk_explicit"


def test_client_reads_tzafon_env_key(monkeypatch):
    monkeypatch.setenv("TZAFON_API_KEY", "sk_from_env")
    c = LightconeClient()
    assert c._sdk.api_key == "sk_from_env"


def test_client_reads_lightcone_alias(monkeypatch):
    monkeypatch.delenv("TZAFON_API_KEY", raising=False)
    monkeypatch.setenv("LIGHTCONE_API_KEY", "sk_alias")
    c = LightconeClient()
    assert c._sdk.api_key == "sk_alias"


# ── ComputerSession properties ────────────────────────────────────────────────

def test_session_id(session, raw_computer):
    assert session.id == raw_computer.id


def test_session_live_view_url(raw_computer, mock_sdk):
    raw_computer.endpoints = {"debug": "/debug/xyz"}
    sess = ComputerSession(raw=raw_computer, sdk=mock_sdk)
    assert sess.live_view_url == "https://api.tzafon.ai/debug/xyz"


def test_session_live_view_url_none_when_missing(raw_computer, mock_sdk):
    raw_computer.endpoints = {}
    sess = ComputerSession(raw=raw_computer, sdk=mock_sdk)
    assert sess.live_view_url is None


def test_session_screencast_url(raw_computer, mock_sdk):
    raw_computer.endpoints = {"screencast": "/screencast/xyz"}
    sess = ComputerSession(raw=raw_computer, sdk=mock_sdk)
    assert sess.screencast_url == "https://api.tzafon.ai/screencast/xyz"


# ── create_computer ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_computer_desktop(client):
    raw = _make_raw_computer("comp_1")
    client._sdk.computers.create.return_value = raw

    sess = await client.create_computer("desktop")

    client._sdk.computers.create.assert_called_once_with(kind="desktop", persistent=False)
    assert isinstance(sess, ComputerSession)
    assert sess.id == "comp_1"


@pytest.mark.asyncio
async def test_create_computer_browser(client):
    raw = _make_raw_computer("comp_b")
    client._sdk.computers.create.return_value = raw

    await client.create_computer("browser")
    client._sdk.computers.create.assert_called_once_with(kind="browser", persistent=False)


@pytest.mark.asyncio
async def test_create_computer_persistent(client):
    raw = _make_raw_computer()
    client._sdk.computers.create.return_value = raw

    await client.create_computer("desktop", persistent=True)
    call_kwargs = client._sdk.computers.create.call_args.kwargs
    assert call_kwargs["persistent"] is True


@pytest.mark.asyncio
async def test_create_computer_with_environment_id(client):
    raw = _make_raw_computer()
    client._sdk.computers.create.return_value = raw

    await client.create_computer("desktop", environment_id="env_42")
    call_kwargs = client._sdk.computers.create.call_args.kwargs
    assert call_kwargs.get("environment_id") == "env_42"


# ── context manager ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_computer_context_manager_cleans_up(client):
    raw = _make_raw_computer("comp_ctx")
    client._sdk.computers.create.return_value = raw

    async with client.computer("desktop") as sess:
        assert sess.id == "comp_ctx"

    client._sdk.computers.delete.assert_called_once_with("comp_ctx")


@pytest.mark.asyncio
async def test_computer_context_manager_cleans_up_on_exception(client):
    raw = _make_raw_computer("comp_err")
    client._sdk.computers.create.return_value = raw

    with pytest.raises(RuntimeError):
        async with client.computer("desktop"):
            raise RuntimeError("boom")

    client._sdk.computers.delete.assert_called_once_with("comp_err")


# ── screenshot ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_screenshot_returns_result(session, mock_sdk):
    raw_shot = MagicMock()
    raw_shot.result = "iVBORw0KGgo="
    raw_shot.page_context = None
    mock_sdk.computers.screenshot.return_value = raw_shot

    result = await session.screenshot()

    assert isinstance(result, ScreenshotResult)
    assert result.b64 == "iVBORw0KGgo="
    mock_sdk.computers.screenshot.assert_called_once_with(session.id, base64=True)


@pytest.mark.asyncio
async def test_screenshot_b64_strips_data_uri(session, mock_sdk):
    raw_shot = MagicMock()
    raw_shot.result = "data:image/png;base64,iVBORw0KGgo="
    raw_shot.page_context = None
    mock_sdk.computers.screenshot.return_value = raw_shot

    b64 = await session.screenshot_b64()
    assert b64 == "iVBORw0KGgo="


@pytest.mark.asyncio
async def test_screenshot_b64_raises_if_no_image(session, mock_sdk):
    raw_shot = MagicMock()
    raw_shot.result = None
    raw_shot.page_context = None
    mock_sdk.computers.screenshot.return_value = raw_shot

    with pytest.raises(RuntimeError, match="no image data"):
        await session.screenshot_b64()


# ── viewport / html / navigate ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_viewport_from_page_context(session, mock_sdk):
    raw_vp = MagicMock()
    ns = types.SimpleNamespace(width=1280, height=720, url="https://ex.com")
    raw_vp.page_context = ns
    raw_vp.result = None
    mock_sdk.computers.viewport.return_value = raw_vp

    result = await session.viewport()
    assert result["width"] == 1280
    assert result["height"] == 720
    mock_sdk.computers.viewport.assert_called_once_with(session.id)


@pytest.mark.asyncio
async def test_viewport_fallback_to_result(session, mock_sdk):
    raw_vp = MagicMock()
    raw_vp.page_context = None
    raw_vp.result = {"width": 800, "height": 600}
    mock_sdk.computers.viewport.return_value = raw_vp

    result = await session.viewport()
    assert result["width"] == 800


@pytest.mark.asyncio
async def test_html(session, mock_sdk):
    raw = MagicMock()
    raw.result = "<html>test</html>"
    mock_sdk.computers.html.return_value = raw

    result = await session.html()
    assert result == "<html>test</html>"
    mock_sdk.computers.html.assert_called_once_with(session.id)


@pytest.mark.asyncio
async def test_navigate(session, mock_sdk):
    mock_sdk.computers.navigate.return_value = _make_action_raw()
    await session.navigate("https://example.com")
    mock_sdk.computers.navigate.assert_called_once_with(session.id, url="https://example.com")


# ── Mouse ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_click(session, mock_sdk):
    mock_sdk.computers.click.return_value = _make_action_raw()
    result = await session.click(100, 200)
    mock_sdk.computers.click.assert_called_once_with(session.id, x=100, y=200)
    assert isinstance(result, ActionResult)
    assert result.ok


@pytest.mark.asyncio
async def test_double_click(session, mock_sdk):
    mock_sdk.computers.double_click.return_value = _make_action_raw()
    await session.double_click(50, 75)
    mock_sdk.computers.double_click.assert_called_once_with(session.id, x=50, y=75)


@pytest.mark.asyncio
async def test_right_click(session, mock_sdk):
    mock_sdk.computers.right_click.return_value = _make_action_raw()
    await session.right_click(10, 20)
    mock_sdk.computers.right_click.assert_called_once_with(session.id, x=10, y=20)


@pytest.mark.asyncio
async def test_drag(session, mock_sdk):
    mock_sdk.computers.drag.return_value = _make_action_raw()
    await session.drag(0, 0, 100, 100)
    mock_sdk.computers.drag.assert_called_once_with(session.id, x=0, y=0, end_x=100, end_y=100)


@pytest.mark.asyncio
async def test_scroll(session, mock_sdk):
    mock_sdk.computers.scroll.return_value = _make_action_raw()
    await session.scroll(400, 300, dy=-5)
    mock_sdk.computers.scroll.assert_called_once_with(session.id, x=400, y=300, dx=0, dy=-5)


@pytest.mark.asyncio
async def test_mouse_down_up(session, mock_sdk):
    mock_sdk.computers.mouse_down.return_value = _make_action_raw()
    mock_sdk.computers.mouse_up.return_value = _make_action_raw()
    await session.mouse_down(100, 200)
    await session.mouse_up(100, 200)
    mock_sdk.computers.mouse_down.assert_called_once_with(session.id, x=100, y=200)
    mock_sdk.computers.mouse_up.assert_called_once_with(session.id, x=100, y=200)


# ── Keyboard ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_type(session, mock_sdk):
    mock_sdk.computers.type.return_value = _make_action_raw()
    await session.type("hello world")
    mock_sdk.computers.type.assert_called_once_with(session.id, text="hello world")


@pytest.mark.asyncio
async def test_hotkey_single_key(session, mock_sdk):
    mock_sdk.computers.hotkey.return_value = _make_action_raw()
    await session.hotkey("Enter")
    mock_sdk.computers.hotkey.assert_called_once_with(session.id, keys=["Enter"])


@pytest.mark.asyncio
async def test_hotkey_combo(session, mock_sdk):
    mock_sdk.computers.hotkey.return_value = _make_action_raw()
    await session.hotkey("ctrl", "a")
    mock_sdk.computers.hotkey.assert_called_once_with(session.id, keys=["ctrl", "a"])


@pytest.mark.asyncio
async def test_key_down_up(session, mock_sdk):
    mock_sdk.computers.key_down.return_value = _make_action_raw()
    mock_sdk.computers.key_up.return_value = _make_action_raw()
    await session.key_down("shift")
    await session.key_up("shift")
    mock_sdk.computers.key_down.assert_called_once_with(session.id, key="shift")
    mock_sdk.computers.key_up.assert_called_once_with(session.id, key="shift")


# ── Shell ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exec_sync(session, mock_sdk):
    raw = MagicMock()
    raw.stdout = "hello\n"
    raw.stderr = ""
    raw.exit_code = 0
    raw.error_message = None
    mock_sdk.computers.exec.sync.return_value = raw

    result = await session.exec_sync("echo hello")

    mock_sdk.computers.exec.sync.assert_called_once_with(session.id, command="echo hello")
    assert isinstance(result, ExecResult)
    assert result.ok
    assert result.stdout == "hello\n"


@pytest.mark.asyncio
async def test_exec_sync_with_options(session, mock_sdk):
    raw = MagicMock()
    raw.stdout = ""
    raw.stderr = ""
    raw.exit_code = 0
    raw.error_message = None
    mock_sdk.computers.exec.sync.return_value = raw

    await session.exec_sync("ls", cwd="/tmp", env={"FOO": "bar"}, timeout_seconds=30)
    mock_sdk.computers.exec.sync.assert_called_once_with(
        session.id,
        command="ls",
        cwd="/tmp",
        env={"FOO": "bar"},
        timeout_seconds=30,
    )


@pytest.mark.asyncio
async def test_exec_sync_failure(session, mock_sdk):
    raw = MagicMock()
    raw.stdout = ""
    raw.stderr = "not found"
    raw.exit_code = 127
    raw.error_message = "command not found"
    mock_sdk.computers.exec.sync.return_value = raw

    result = await session.exec_sync("badcmd")
    assert not result.ok
    assert result.exit_code == 127


@pytest.mark.asyncio
async def test_exec_stream(session, mock_sdk):
    async def _fake_stream():
        yield types.SimpleNamespace(type="stdout", line="line1")
        yield types.SimpleNamespace(type="exit_code", exit_code=0)

    mock_sdk.computers.exec.create.return_value = _fake_stream()

    chunks = [c async for c in session.exec_stream("tail -f /var/log/syslog")]
    assert len(chunks) == 2
    assert chunks[0]["type"] == "stdout"


# ── Batch ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch(session, mock_sdk):
    mock_sdk.computers.batch.return_value = [{"status": "ok"}, {"status": "ok"}]
    actions = [
        {"type": "click", "x": 100, "y": 200},
        {"type": "type", "text": "hello"},
    ]
    results = await session.batch(actions)
    assert len(results) == 2
    mock_sdk.computers.batch.assert_called_once_with(session.id, actions)


# ── Tabs ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tabs(session, mock_sdk):
    mock_sdk.computers.tabs.list.return_value = ["tab1", "tab2"]
    tabs = await session.list_tabs()
    assert tabs == ["tab1", "tab2"]
    mock_sdk.computers.tabs.list.assert_called_once_with(session.id)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_keepalive(session, mock_sdk):
    await session.keepalive()
    mock_sdk.computers.keepalive.assert_called_once_with(session.id)


@pytest.mark.asyncio
async def test_session_delete(session, mock_sdk):
    await session.delete()
    mock_sdk.computers.delete.assert_called_once_with(session.id)


@pytest.mark.asyncio
async def test_session_delete_swallows_error(session, mock_sdk):
    mock_sdk.computers.delete.side_effect = Exception("already gone")
    await session.delete()  # must not raise


@pytest.mark.asyncio
async def test_session_async_context_manager(raw_computer, mock_sdk):
    sess = ComputerSession(raw=raw_computer, sdk=mock_sdk)
    async with sess as s:
        assert s is sess
    mock_sdk.computers.delete.assert_called_once_with(raw_computer.id)


# ── ActionResult ──────────────────────────────────────────────────────────────

def test_action_result_ok():
    r = ActionResult(status="success")
    assert r.ok


def test_action_result_not_ok_on_error():
    r = ActionResult(status="success", error_message="oops")
    assert not r.ok


def test_action_result_not_ok_on_bad_status():
    r = ActionResult(status="error")
    assert not r.ok


# ── create_persistent_computer ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_persistent_computer(client):
    raw = _make_raw_computer("env_001")
    client._sdk.computers.create.return_value = raw
    client._sdk.computers.exec = MagicMock()
    client._sdk.computers.exec.sync = AsyncMock()

    sess = await client.create_persistent_computer(kind="desktop", setup_command="apt-get install -y curl")

    assert sess.id == "env_001"
    client._sdk.computers.exec.sync.assert_called_once()
    call_kwargs = client._sdk.computers.exec.sync.call_args
    assert call_kwargs[0][0] == "env_001"  # positional computer id


@pytest.mark.asyncio
async def test_create_persistent_computer_no_setup(client):
    raw = _make_raw_computer("env_002")
    client._sdk.computers.create.return_value = raw

    sess = await client.create_persistent_computer(kind="browser")

    assert sess.id == "env_002"
    client._sdk.computers.exec.sync.assert_not_called()


# ── Task API ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_task_yields_events(client):
    async def _fake_stream():
        for ev in [
            MagicMock(type="action", message="Clicking button", text=None, kind="", event=""),
            MagicMock(type="status", message="completed", text=None, kind="", event=""),
        ]:
            yield ev

    client._sdk.agent.tasks.start_stream.return_value = _fake_stream()

    events = []
    async for e in client.run_task("Do something"):
        events.append(e)

    assert len(events) == 2
    assert all(isinstance(e, TaskEvent) for e in events)
    assert events[0].kind == "action"
    assert events[0].step == 1
    assert events[1].kind == "status"


@pytest.mark.asyncio
async def test_run_task_passes_params(client):
    async def _empty():
        return
        yield

    client._sdk.agent.tasks.start_stream.return_value = _empty()

    async for _ in client.run_task(
        "test task",
        kind="browser",
        max_steps=50,
        temperature=0.5,
        environment_id="env_xyz",
    ):
        pass

    kw = client._sdk.agent.tasks.start_stream.call_args.kwargs
    assert kw["instruction"] == "test task"
    assert kw["kind"] == "browser"
    assert kw["max_steps"] == 50
    assert kw["temperature"] == 0.5
    assert kw["environment_id"] == "env_xyz"


@pytest.mark.asyncio
async def test_run_task_collect_returns_agent_result(client):
    async def _fake_stream():
        yield MagicMock(type="action", message="step 1", text=None, kind="", event="")
        yield MagicMock(type="answer", message="The answer is 42", text=None, kind="answer", event="")

    client._sdk.agent.tasks.start_stream.return_value = _fake_stream()

    result = await client.run_task_collect("What is 6*7?", verbose=False)
    assert isinstance(result, AgentResult)
    assert result.answer == "The answer is 42"
    assert result.steps == 2


@pytest.mark.asyncio
async def test_run_task_on_environment(client):
    async def _fake_stream():
        yield MagicMock(type="done", message="done", text=None, kind="done", event="")

    client._sdk.agent.tasks.start_stream.return_value = _fake_stream()

    result = await client.run_task_on_environment(
        "Open Firefox", environment_id="env_persist", verbose=False
    )
    kw = client._sdk.agent.tasks.start_stream.call_args.kwargs
    assert kw["environment_id"] == "env_persist"
    assert isinstance(result, AgentResult)


@pytest.mark.asyncio
async def test_batch_run_tasks_sequential(client):
    call_count = 0

    async def _fake_stream():
        nonlocal call_count
        call_count += 1
        yield MagicMock(type="done", message=f"done {call_count}", text=None, kind="done", event="")

    client._sdk.agent.tasks.start_stream.side_effect = lambda **kw: _fake_stream()

    records = [{"name": "Alice"}, {"name": "Bob"}]
    results = await client.batch_run_tasks(
        records,
        instruction_template="Create user {name}",
        kind="desktop",
    )

    assert len(results) == 2
    assert client._sdk.agent.tasks.start_stream.call_count == 2
    first_call = client._sdk.agent.tasks.start_stream.call_args_list[0].kwargs
    assert "Alice" in first_call["instruction"]


@pytest.mark.asyncio
async def test_batch_run_tasks_concurrent(client):
    async def _fake_stream(**kw):
        yield MagicMock(type="done", message="done", text=None, kind="done", event="")

    client._sdk.agent.tasks.start_stream.side_effect = lambda **kw: _fake_stream(**kw)

    records = [{"n": str(i)} for i in range(3)]
    results = await client.batch_run_tasks(
        records,
        instruction_template="Task {n}",
        concurrency=3,
    )
    assert len(results) == 3


@pytest.mark.asyncio
async def test_start_task_async(client):
    mock_task = MagicMock()
    mock_task.task_id = "task_999"
    client._sdk.agent.tasks.start.return_value = mock_task

    handle = await client.start_task_async("Run a report")
    assert isinstance(handle, TaskHandle)
    assert handle.task_id == "task_999"


@pytest.mark.asyncio
async def test_task_handle_status(client):
    raw = MagicMock()
    raw.status = "completed"
    raw.exit_code = 0
    client._sdk.agent.tasks.retrieve_status.return_value = raw

    result = await client.get_task_status("task_123")
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_task_handle_pause_resume(client):
    mock_task = MagicMock()
    mock_task.task_id = "task_42"
    client._sdk.agent.tasks.start.return_value = mock_task
    handle = await client.start_task_async("task")

    await handle.pause()
    client._sdk.agent.tasks.pause.assert_called_once_with("task_42")

    await handle.resume()
    client._sdk.agent.tasks.resume.assert_called_once_with("task_42")


@pytest.mark.asyncio
async def test_task_handle_inject(client):
    mock_task = MagicMock()
    mock_task.task_id = "task_77"
    client._sdk.agent.tasks.start.return_value = mock_task
    handle = await client.start_task_async("task")

    await handle.inject("click the blue button")
    client._sdk.agent.tasks.inject_message.assert_called_once_with(
        "task_77", "click the blue button"
    )


# ── Responses API ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_responses_create(client):
    mock_resp = MagicMock()
    mock_resp.id = "resp_abc"
    client._sdk.responses.create.return_value = mock_resp

    result = await client.responses_create(model="tzafon.northstar-cua-fast", input=[], tools=[])

    client._sdk.responses.create.assert_called_once_with(
        model="tzafon.northstar-cua-fast", input=[], tools=[]
    )
    assert result.id == "resp_abc"
