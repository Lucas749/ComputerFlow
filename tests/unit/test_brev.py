"""
Unit tests for backend/app/infra/brev.py.

All subprocess / HTTP calls are mocked — no Brev CLI, no network required.
"""

import json
import subprocess
import sys
import os
from unittest.mock import MagicMock, patch

import pytest
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from app.infra.brev import BrevClient, BrevInstance, NIMClient, NIMResponse


# ── BrevClient ────────────────────────────────────────────────────────────────

@pytest.fixture
def brev():
    return BrevClient()


def _make_run(stdout="", returncode=0, stderr=""):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = stderr
    return result


def test_list_instances_parses_json(brev):
    data = [
        {"id": "i1", "name": "gpu-box", "status": "running", "gpu": "a10g", "ip": "1.2.3.4"},
        {"id": "i2", "name": "dev-box", "status": "stopped", "gpu": "h100"},
    ]
    with patch("subprocess.run", return_value=_make_run(json.dumps(data))):
        instances = brev.list_instances()

    assert len(instances) == 2
    assert instances[0].id == "i1"
    assert instances[0].name == "gpu-box"
    assert instances[0].status == "running"
    assert instances[0].ip == "1.2.3.4"
    assert instances[1].ip is None


def test_list_instances_empty_output(brev):
    with patch("subprocess.run", return_value=_make_run("")):
        instances = brev.list_instances()
    assert instances == []


def test_list_instances_invalid_json(brev):
    with patch("subprocess.run", return_value=_make_run("not json")):
        instances = brev.list_instances()
    assert instances == []


def test_get_instance_found(brev):
    data = [{"id": "i1", "name": "gpu-box", "status": "running", "gpu": "a10g"}]
    with patch("subprocess.run", return_value=_make_run(json.dumps(data))):
        inst = brev.get_instance("gpu-box")
    assert inst is not None
    assert inst.id == "i1"


def test_get_instance_not_found(brev):
    with patch("subprocess.run", return_value=_make_run("[]")):
        inst = brev.get_instance("nonexistent")
    assert inst is None


def test_start_instance_calls_open(brev):
    with patch("subprocess.run", return_value=_make_run("{}")) as mock_run:
        brev.start_instance("gpu-box")
    mock_run.assert_called_once()
    args = mock_run.call_args.args[0]
    assert "open" in args
    assert "gpu-box" in args


def test_stop_instance_calls_stop(brev):
    with patch("subprocess.run", return_value=_make_run("{}")) as mock_run:
        brev.stop_instance("gpu-box")
    args = mock_run.call_args.args[0]
    assert "stop" in args


def test_delete_instance(brev):
    with patch("subprocess.run", return_value=_make_run("{}")) as mock_run:
        brev.delete_instance("gpu-box")
    args = mock_run.call_args.args[0]
    assert "delete" in args


def test_create_launchable(brev):
    data = {"id": "i99", "name": "new-box", "status": "starting", "gpu": "h100"}
    with patch("subprocess.run", return_value=_make_run(json.dumps(data))) as mock_run:
        inst = brev.create_launchable("new-box", "h100", ports=[8000])

    assert inst.name == "new-box"
    assert inst.gpu == "h100"
    args = mock_run.call_args.args[0]
    assert "create" in args
    assert "new-box" in args
    assert "8000" in args


def test_brev_cli_not_found_raises(brev):
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="brev CLI not found"):
            brev.list_instances()


def test_brev_cli_error_raises(brev):
    err_result = _make_run("", returncode=1, stderr="instance not found")
    with patch("subprocess.run", return_value=err_result):
        with pytest.raises(RuntimeError, match="brev CLI error"):
            brev.start_instance("missing")


def test_ssh_command(brev):
    with patch("subprocess.run", return_value=_make_run("total 42\n")) as mock_run:
        code, stdout, _ = brev.ssh_command("gpu-box", "ls -la")
    assert code == 0
    assert "total" in stdout


# ── NIMClient ─────────────────────────────────────────────────────────────────

@pytest.fixture
def nim():
    return NIMClient(base_url="http://nim.local:8000/v1", api_key="test-key")


def _nim_chat_response(content="Hello!", model="llama-3"):
    return {
        "id": "chatcmpl-123",
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_nim_chat_success(nim, respx_mock=None):
    response_data = _nim_chat_response("Hi there!")

    with patch.object(nim, "_post", return_value=response_data) as mock_post:
        result = nim.chat(
            "meta/llama-3.1-8b-instruct",
            [{"role": "user", "content": "Hello"}],
        )

    assert isinstance(result, NIMResponse)
    assert result.content == "Hi there!"
    assert result.finish_reason == "stop"
    assert result.usage["total_tokens"] == 15

    call_body = mock_post.call_args.args[1]
    assert call_body["model"] == "meta/llama-3.1-8b-instruct"
    assert call_body["messages"][0]["role"] == "user"


def test_nim_chat_with_nim_message_objects(nim):
    from app.infra.brev import NIMMessage
    response_data = _nim_chat_response("Response")

    with patch.object(nim, "_post", return_value=response_data):
        result = nim.chat(
            "some-model",
            [NIMMessage(role="user", content="test")],
        )
    assert result.content == "Response"


def test_nim_chat_custom_params(nim):
    response_data = _nim_chat_response()

    with patch.object(nim, "_post", return_value=response_data) as mock_post:
        nim.chat("model", [{"role": "user", "content": "hi"}], max_tokens=2048, temperature=0.7)

    body = mock_post.call_args.args[1]
    assert body["max_tokens"] == 2048
    assert body["temperature"] == 0.7


def test_nim_embeddings(nim):
    response_data = {
        "data": [
            {"embedding": [0.1, 0.2, 0.3], "index": 0},
            {"embedding": [0.4, 0.5, 0.6], "index": 1},
        ]
    }

    with patch.object(nim, "_post", return_value=response_data):
        vecs = nim.embeddings("embed-model", ["text1", "text2"])

    assert len(vecs) == 2
    assert vecs[0] == [0.1, 0.2, 0.3]


def test_nim_embeddings_single_string(nim):
    response_data = {"data": [{"embedding": [0.9, 0.8], "index": 0}]}

    with patch.object(nim, "_post", return_value=response_data) as mock_post:
        vecs = nim.embeddings("embed-model", "single text")

    body = mock_post.call_args.args[1]
    assert body["input"] == ["single text"]
    assert len(vecs) == 1


def test_nim_models(nim):
    models_data = {
        "data": [
            {"id": "meta/llama-3.1-8b-instruct", "object": "model"},
            {"id": "nvidia/nemotron-70b", "object": "model"},
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = models_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = nim.models()

    assert len(result) == 2
    assert result[0]["id"] == "meta/llama-3.1-8b-instruct"


def test_nim_default_base_url(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nv_key")
    monkeypatch.delenv("NIM_BASE_URL", raising=False)
    nim = NIMClient()
    assert "nvidia.com" in nim._base_url


def test_nim_env_base_url(monkeypatch):
    monkeypatch.setenv("NIM_BASE_URL", "http://custom.nim:8080/v1")
    nim = NIMClient()
    assert nim._base_url == "http://custom.nim:8080/v1"


def test_nim_post_raises_on_http_error(nim):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            nim.chat("model", [{"role": "user", "content": "hi"}])
