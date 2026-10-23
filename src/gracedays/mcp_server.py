from __future__ import annotations

import json
from datetime import date
from typing import Any

from mcp.server import MCPServer
from pydantic import ValidationError

from gracedays.clock import Clock
from gracedays.config import Settings
from gracedays.models import PurchaseSaveRequest
from gracedays.services.deadlines import decorate_deadlines, derive_state
from gracedays.services.demo import build_demo_records
from gracedays.services.drafts import draft_action_message as build_message_draft
from gracedays.turso_db import TursoDatabase

AGENT_TOOLS = frozenset({
    "list_purchases", "list_deadlines", "get_purchase_details",
    "update_purchase_status", "draft_action_message",
})
UI_TOOLS = frozenset({"save_purchase", "delete_purchase", "update_deadline_status"})
ADMIN_TOOLS = frozenset({"seed_demo_data", "reset_demo_data"})


def create_mcp_server(settings: Settings | None = None, database: TursoDatabase | None = None, **legacy_kwargs: Any) -> MCPServer:
    settings = settings or Settings.from_env()
    # Accept the old keyword temporarily for callers that still use create_mcp_server(worker=...).
    database = database or legacy_kwargs.get("worker") or TursoDatabase(settings.turso_database_url, settings.turso_auth_token)
    clock = Clock(settings.timezone, settings.fake_today)
    server = MCPServer(settings.app_name)

    @server.tool()
    def health_check() -> dict[str, Any]:
        """Check the MCP server and direct Turso database connection."""
        try:
            database_health = database.health()
        except Exception as exc:
            database_health = {"status": "unavailable", "detail": str(exc)[:300]}
        return {
            "status": "healthy",
            "service": settings.app_name,
            "as_of_date": clock.today().isoformat(),
            "timezone": clock.timezone_name,
            "database": database_health,
        }

    @server.tool()
    def list_purchases(query: str = "", limit: int = 20) -> dict[str, Any]:
        """List saved purchases, optionally filtered by product, merchant, or order reference."""
        if len(query) > 100 or not 1 <= limit <= 100:
            raise ValueError("query must be <= 100 characters and limit must be 1..100")
        response = database.list_purchases(query=query, limit=limit)
        return {
            "purchases": response.get("purchases", []),
            "count": len(response.get("purchases", [])),
            "as_of_date": clock.today().isoformat(),
            "timezone": clock.timezone_name,
        }

    @server.tool()
    def list_deadlines(within_days: int = 7, include_closed: bool = False) -> dict[str, Any]:
        """List deadlines needing attention, ordered overdue first then today and upcoming."""
        if not 0 <= within_days <= 3650:
            raise ValueError("within_days must be between 0 and 3650")
        response = database.list_deadlines(include_closed=include_closed)
        rows = decorate_deadlines(response.get("deadlines", []), clock, within_days, include_closed)
        return {
            "deadlines": rows,
            "count": len(rows),
            "as_of_date": clock.today().isoformat(),
            "timezone": clock.timezone_name,
            "window_days": within_days,
        }

    @server.tool()
    def get_purchase_details(purchase_id: str) -> dict[str, Any]:
        """Get one saved purchase with its deadlines and verified evidence records."""
        if not purchase_id or len(purchase_id) > 80:
            raise ValueError("A valid purchase_id is required")
        response = database.get_purchase(purchase_id)
        purchase = response.get("purchase", response)
        deadlines = response.get("deadlines", purchase.get("deadlines", []))
        evidence = response.get("evidence", [])
        decorated = []
        for deadline in deadlines:
            row = dict(deadline)
            row["derived_state"] = derive_state(row, purchase.get("status", "active"), clock.today())
            row["days_remaining"] = (date.fromisoformat(row["due_date"]) - clock.today()).days
            decorated.append(row)
        return {
            "purchase": purchase,
            "deadlines": decorated,
            "evidence": evidence,
            "as_of_date": clock.today().isoformat(),
            "timezone": clock.timezone_name,
        }

    @server.tool()
    def update_purchase_status(purchase_id: str, status: str) -> dict[str, Any]:
        """Update the status of one saved purchase; no external action is performed."""
        if not purchase_id or len(purchase_id) > 80:
            raise ValueError("A valid purchase_id is required")
        if status not in {"active", "returned", "cancelled", "resolved"}:
            raise ValueError("status must be active, returned, cancelled, or resolved")
        response = database.update_purchase_status(purchase_id, status)
        return {**response, "external_action_performed": False}

    @server.tool()
    def update_deadline_status(deadline_id: str, status: str) -> dict[str, Any]:
        """UI-only: update a saved deadline's status, without changing its date or evidence."""
        if not deadline_id or len(deadline_id) > 80:
            raise ValueError("A valid deadline_id is required")

        if status not in {"open", "completed", "dismissed"}:
            raise ValueError("status must be open, completed, or dismissed")

        result = database.update_deadline_status(deadline_id, status)
        return {**result, "external_action_performed": False}

    @server.tool()
    def draft_action_message(purchase_id: str, action_type: str) -> dict[str, Any]:
        """Draft (but never send) a return or cancellation message from saved purchase facts."""
        if action_type not in {"return", "cancellation"}:
            raise ValueError("action_type must be return or cancellation")
        response = database.get_purchase(purchase_id)
        purchase = response.get("purchase", response)
        purchase["deadlines"] = response.get("deadlines", purchase.get("deadlines", []))
        draft = build_message_draft(purchase, action_type, clock.today())
        return {**draft, "purchase_id": purchase_id, "created_at": None}

    @server.tool()
    def save_purchase(purchase_json: str, confirmed: bool) -> dict[str, Any]:
        """UI-only: persist a reviewed purchase only after the user's explicit confirmation."""
        if confirmed is not True:
            raise ValueError("Explicit user confirmation is required before saving")
        if len(purchase_json) > 100_000:
            raise ValueError("Purchase payload is too large")
        try:
            parsed = PurchaseSaveRequest.model_validate_json(purchase_json)
        except (ValidationError, ValueError) as exc:
            raise ValueError(f"Invalid purchase payload: {exc}") from exc
        # Independently re-check verbatim evidence before persistence.
        from gracedays.evidence import verify_excerpt
        for item in parsed.evidence:
            manual = item.verification_status.value == "user_entered" and item.source_excerpt.startswith("Entered manually by you on ")
            if not manual and not verify_excerpt(parsed.source_text, item.source_excerpt):
                raise ValueError(f"Evidence excerpt for {item.field_name} is not present in source text")
        for deadline in parsed.deadlines:
            manual = deadline.verification.value == "user_entered" and deadline.evidence_excerpt.startswith("Entered manually by you on ")
            if not manual and not verify_excerpt(parsed.source_text, deadline.evidence_excerpt):
                raise ValueError(f"Deadline evidence for {deadline.deadline_type.value} is not present in source text")
        payload = parsed.model_dump(mode="json")
        response = database.save_purchase(payload)
        return {**response, "confirmed_by_user": True}

    @server.tool()
    def delete_purchase(purchase_id: str, confirm_phrase: str) -> dict[str, Any]:
        """UI-only: permanently delete one purchase after the user types DELETE in the confirmation dialog."""
        if confirm_phrase != "DELETE":
            raise ValueError("Deletion requires the explicit confirmation phrase DELETE")
        if not purchase_id or len(purchase_id) > 80:
            raise ValueError("A valid purchase_id is required")
        return database.delete_purchase(purchase_id)

    @server.tool()
    def seed_demo_data() -> dict[str, Any]:
        """Admin/UI-only: replace synthetic demo records with fresh date-relative examples."""
        records = build_demo_records(settings)
        result = database.seed_demo(records)
        return {**result, "synthetic_only": True}

    @server.tool()
    def reset_demo_data(confirm_phrase: str) -> dict[str, Any]:
        """Admin/UI-only: remove demo records only; non-demo purchases are preserved."""
        if confirm_phrase != "RESET DEMO DATA":
            raise ValueError("Type RESET DEMO DATA to confirm demo reset")
        return database.reset_demo()

    return server


def draft_action_message_for_record(purchase: dict[str, Any], action_type: str, today: date) -> dict[str, str]:
    return build_message_draft(purchase, action_type, today)


def main() -> None:
    settings = Settings.from_env()
    if settings.mcp_host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("MCP server must bind to loopback; configure MCP_HOST=127.0.0.1")
    server = create_mcp_server(settings)
    server.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
