from gracedays.clock import Clock
from gracedays.orchestrator import AGENT_TOOL_ALLOWLIST, AgentOrchestrator
from gracedays.providers.base import AgentTurn, ToolCall
from gracedays.providers.mock import MockProvider


class FakeGateway:
    def __init__(self):
        self.calls = []

    def list_tools(self):
        names = [
            "list_purchases", "list_deadlines", "get_purchase_details", "update_purchase_status",
            "draft_action_message", "save_purchase", "delete_purchase", "seed_demo_data", "reset_demo_data", "health_check",
        ]
        return {"protocol_version": "2026-07-28", "tools": [{"name": name, "description": name, "inputSchema": {"type": "object", "properties": {}}} for name in names]}

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"purchases": []}


class MaliciousProvider:
    name = "test"
    def __init__(self):
        self.steps = 0
    def extract(self, source_text):
        raise NotImplementedError
    def chat(self, messages, tools):
        self.steps += 1
        if self.steps == 1:
            return AgentTurn(tool_calls=[ToolCall(id="bad1", name="save_purchase", arguments={"purchase_json": "{}", "confirmed": True})])
        return AgentTurn(content="I can't save through chat.")


def test_agent_allowlist_excludes_ui_and_admin_tools():
    assert AGENT_TOOL_ALLOWLIST == {
        "list_purchases", "list_deadlines", "get_purchase_details", "update_purchase_status", "draft_action_message"
    }
    assert "save_purchase" not in AGENT_TOOL_ALLOWLIST
    assert "delete_purchase" not in AGENT_TOOL_ALLOWLIST
    assert "seed_demo_data" not in AGENT_TOOL_ALLOWLIST
    assert "reset_demo_data" not in AGENT_TOOL_ALLOWLIST


def test_orchestrator_blocks_forbidden_tool_calls_in_actual_execution_path():
    gateway = FakeGateway()
    agent = AgentOrchestrator(gateway, MaliciousProvider(), Clock(fake_today="2026-10-22"))
    result = agent.ask("Please save this purchase.")
    assert result["tool_activity"][0]["status"] == "blocked"
    assert gateway.calls == []
