from __future__ import annotations

import asyncio
import json
from typing import Any

try:
    from mcp import Client as _MCPClient
except ImportError:  # Allows offline unit tests to import the orchestration layer.
    _MCPClient = None


class MCPGatewayError(RuntimeError):
    pass


def _value(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
        if isinstance(obj, dict) and name in obj:
            return obj[name]
    return default


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if hasattr(value, "dict") and callable(value.dict):
        return value.dict()
    return value


def _decode_tool_result(result: Any) -> Any:
    is_error = bool(_value(result, "is_error", "isError", default=False))
    if is_error:
        content = _value(result, "content", default=[]) or []
        text = " ".join(str(_value(item, "text", default="")) for item in content).strip()
        raise MCPGatewayError(text or "MCP tool call returned an error")
    structured = _value(result, "structured_content", "structuredContent")
    if structured is not None:
        return structured
    content = _value(result, "content", default=[]) or []
    strings = [str(_value(item, "text", default="")) for item in content if _value(item, "text", default=None) is not None]
    if len(strings) == 1:
        try:
            return json.loads(strings[0])
        except json.JSONDecodeError:
            return strings[0]
    return strings


class McpGateway:
    """Synchronous facade over short-lived official MCP Client sessions."""

    def __init__(self, server_url: str, timeout_seconds: float = 12.0) -> None:
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds

    def _run(self, awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        # Streamlit normally runs outside an active asyncio loop. This branch is
        # useful for tests and embedding the gateway into async applications.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, awaitable).result(timeout=self.timeout_seconds)

    async def _list_tools_async(self) -> dict[str, Any]:
        if _MCPClient is None:
            raise MCPGatewayError("The official MCP SDK is not installed. Install src/requirements.txt to connect to the MCP server.")
        try:
            async with _MCPClient(self.server_url) as client:
                response = await client.list_tools()
                tools = _value(response, "tools", default=response)
                raw_tools = []
                for tool in tools or []:
                    schema = _value(tool, "input_schema", "inputSchema", default={}) or {}
                    raw_tools.append({
                        "name": _value(tool, "name", default=""),
                        "description": _value(tool, "description", default="") or "",
                        "inputSchema": _jsonable(schema) or {},
                    })
                protocol = _value(client, "protocol_version", default=None)
                return {"tools": raw_tools, "protocol_version": str(protocol) if protocol else None}
        except Exception as exc:
            raise MCPGatewayError(f"Could not discover MCP tools at {self.server_url}: {exc}") from exc

    def list_tools(self) -> dict[str, Any]:
        return self._run(self._list_tools_async())

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        if _MCPClient is None:
            raise MCPGatewayError("The official MCP SDK is not installed. Install src/requirements.txt to call MCP tools.")
        try:
            async with _MCPClient(self.server_url) as client:
                result = await client.call_tool(name, arguments)
                return _decode_tool_result(result)
        except MCPGatewayError:
            raise
        except Exception as exc:
            raise MCPGatewayError(f"MCP tool '{name}' failed: {exc}") from exc

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self._run(self._call_tool_async(name, arguments or {}))

    def health_check(self) -> Any:
        return self.call_tool("health_check", {})
