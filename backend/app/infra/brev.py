"""
NVIDIA Brev infrastructure client.

Provides two classes:

BrevClient
    Manages Brev GPU instances via the Brev CLI (subprocess wrapper).
    Use to launch / stop / list instances for self-hosted inference workloads.

NIMClient
    Calls NVIDIA Inference Microservices (NIM) endpoints.
    NIM endpoints expose an OpenAI-compatible REST API, so this client
    is a thin httpx wrapper that works with any NIM running on Brev or elsewhere.

Usage
-----
    # Run a NIM inference call on a Brev-hosted endpoint
    nim = NIMClient(base_url="http://<brev-instance-ip>:8000/v1", api_key="<nim-key>")
    response = nim.chat("meta/llama-3.1-8b-instruct", [{"role": "user", "content": "Hello"}])

    # Manage Brev instances
    brev = BrevClient()
    instances = brev.list_instances()
    brev.start_instance("my-gpu-instance")
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

import httpx


# ── BrevClient ────────────────────────────────────────────────────────────────

@dataclass
class BrevInstance:
    id: str
    name: str
    status: str
    gpu: str = ""
    ip: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


class BrevClient:
    """
    Thin wrapper around the `brev` CLI for GPU instance management.

    Requires `brev` to be installed and authenticated on the host machine.
    Install: https://docs.nvidia.com/brev/latest/getting-started/overview
    """

    def __init__(self, workspace: str | None = None) -> None:
        self._workspace = workspace or os.environ.get("BREV_WORKSPACE")
        self._brev_bin = os.environ.get("BREV_BIN", "brev")

    def _run(self, *args: str, check: bool = True) -> str:
        cmd = [self._brev_bin, *args, "--json"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        except FileNotFoundError:
            raise RuntimeError(
                "brev CLI not found. Install it from https://docs.nvidia.com/brev/latest"
            ) from None
        if check and result.returncode != 0:
            raise RuntimeError(f"brev CLI error: {result.stderr.strip()}")
        return result.stdout.strip()

    def list_instances(self) -> list[BrevInstance]:
        """Return all instances in the current workspace."""
        raw_json = self._run("ls")
        try:
            data = json.loads(raw_json) if raw_json else []
        except json.JSONDecodeError:
            return []
        instances = []
        for item in (data if isinstance(data, list) else [data]):
            instances.append(BrevInstance(
                id=item.get("id", ""),
                name=item.get("name", ""),
                status=item.get("status", ""),
                gpu=item.get("gpu", ""),
                ip=item.get("ip") or item.get("dns"),
                raw=item,
            ))
        return instances

    def get_instance(self, name_or_id: str) -> BrevInstance | None:
        """Return a single instance by name or ID, or None if not found."""
        for inst in self.list_instances():
            if inst.id == name_or_id or inst.name == name_or_id:
                return inst
        return None

    def start_instance(self, name_or_id: str) -> None:
        """Start (open) a stopped Brev instance."""
        self._run("open", name_or_id)

    def stop_instance(self, name_or_id: str) -> None:
        """Stop a running Brev instance (does NOT delete it)."""
        self._run("stop", name_or_id)

    def create_launchable(
        self,
        name: str,
        gpu: str,
        container_image: str | None = None,
        ports: list[int] | None = None,
    ) -> BrevInstance:
        """
        Create a new instance from a Launchable spec.

        gpu examples: "nvidia-a10g", "nvidia-h100-80gb-hbm3"
        """
        args = ["create", name, "--gpu", gpu]
        if container_image:
            args += ["--container-image", container_image]
        if ports:
            for p in ports:
                args += ["--port", str(p)]
        raw_json = self._run(*args)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            data = {}
        return BrevInstance(
            id=data.get("id", ""),
            name=data.get("name", name),
            status=data.get("status", "starting"),
            gpu=data.get("gpu", gpu),
            ip=data.get("ip") or data.get("dns"),
            raw=data,
        )

    def delete_instance(self, name_or_id: str) -> None:
        self._run("delete", name_or_id)

    def ssh_command(self, name_or_id: str, command: str) -> tuple[int, str, str]:
        """
        Run a shell command on the remote instance via SSH.
        Returns (exit_code, stdout, stderr).
        """
        cmd = [self._brev_bin, "ssh", name_or_id, "--", command]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr


# ── NIMClient ─────────────────────────────────────────────────────────────────

@dataclass
class NIMMessage:
    role: str
    content: str


@dataclass
class NIMResponse:
    model: str
    content: str
    finish_reason: str
    usage: dict[str, int]
    raw: dict = field(default_factory=dict, repr=False)


class NIMClient:
    """
    Client for NVIDIA Inference Microservice (NIM) endpoints.

    NIM exposes an OpenAI-compatible REST API at /v1. Works with any NIM
    endpoint — whether hosted on Brev, NVIDIA Cloud, or locally.

    Args
    ----
    base_url:  Base URL of the NIM endpoint, e.g. "http://10.0.0.5:8000/v1"
               or "https://integrate.api.nvidia.com/v1" for NVIDIA-hosted NIMs.
    api_key:   API key (required for NVIDIA-hosted NIMs; may be optional for
               self-hosted instances).
    timeout:   Request timeout in seconds. Default 120.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("NIM_BASE_URL")
            or "https://integrate.api.nvidia.com/v1"
        ).rstrip("/")
        key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self._headers = {"Content-Type": "application/json"}
        if key:
            self._headers["Authorization"] = f"Bearer {key}"
        self._timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, json=body, headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    def chat(
        self,
        model: str,
        messages: list[dict | NIMMessage],
        max_tokens: int = 1024,
        temperature: float = 0.2,
        top_p: float = 1.0,
        stream: bool = False,
        extra: dict | None = None,
    ) -> NIMResponse:
        """
        Chat completion via /v1/chat/completions.

        model examples:
          "meta/llama-3.1-8b-instruct"
          "nvidia/llama-3.1-nemotron-70b-instruct"
          "microsoft/phi-3.5-mini-instruct"

        messages: list of {"role": "user"|"system"|"assistant", "content": "..."}
        """
        normalized = [
            m if isinstance(m, dict) else {"role": m.role, "content": m.content}
            for m in messages
        ]
        body: dict[str, Any] = {
            "model": model,
            "messages": normalized,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
        }
        if extra:
            body.update(extra)

        data = self._post("/chat/completions", body)
        choice = data["choices"][0]
        return NIMResponse(
            model=data.get("model", model),
            content=choice["message"]["content"],
            finish_reason=choice.get("finish_reason", ""),
            usage=data.get("usage", {}),
            raw=data,
        )

    def embeddings(
        self,
        model: str,
        input: str | list[str],
        encoding_format: str = "float",
    ) -> list[list[float]]:
        """
        Text embeddings via /v1/embeddings.
        Returns list of embedding vectors (one per input string).
        """
        body = {
            "model": model,
            "input": input if isinstance(input, list) else [input],
            "encoding_format": encoding_format,
        }
        data = self._post("/embeddings", body)
        return [item["embedding"] for item in data["data"]]

    def models(self) -> list[dict]:
        """List available models on this NIM endpoint."""
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self._base_url}/models",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
