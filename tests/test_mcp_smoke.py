from __future__ import annotations

import os
import importlib.util
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gracedays.gateway import McpGateway


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_real_mcp_streamable_http_tools_list_and_call():
    if importlib.util.find_spec("mcp") is None:
        pytest.skip("Official MCP SDK unavailable in this offline test container; installed project dependencies enable this HTTP integration test.")
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["MCP_HOST"] = "127.0.0.1"
    env["MCP_PORT"] = str(port)
    env["MCP_SERVER_URL"] = f"http://127.0.0.1:{port}/mcp"
    env.pop("GRACEDAYS_SHARED_SECRET", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "gracedays.mcp_server"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    gateway = McpGateway(f"http://127.0.0.1:{port}/mcp")
    try:
        last_error = None
        discovered = None
        for _ in range(60):
            if process.poll() is not None:
                break
            try:
                discovered = gateway.list_tools()
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.25)
        if discovered is None:
            stderr = ""
            if process.poll() is not None and process.stderr:
                stderr = process.stderr.read()[-4000:]
            pytest.fail(f"MCP Streamable HTTP endpoint did not become ready: {last_error}\n{stderr}")
        names = {tool["name"] for tool in discovered["tools"]}
        assert "health_check" in names
        assert {"list_purchases", "list_deadlines", "get_purchase_details", "update_purchase_status", "draft_action_message"}.issubset(names)
        result = gateway.call_tool("health_check", {})
        assert result["status"] == "healthy"
        # The v2 SDK negotiates a current MCP protocol; some clients expose it as None
        # until first response, so assert its shape only when the SDK reports it.
        version = discovered.get("protocol_version")
        if version and version[0].isdigit():
            assert version >= "2025-11-25"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
