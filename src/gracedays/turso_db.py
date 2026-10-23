"""Turso Cloud persistence for GraceDays.

All SQL operations live here. The rest of the application calls this repository
through its small CRUD API; it does not need to know about HTTP, auth headers,
Cloudflare Workers, or SQL statements.

Requires the official Turso remote DB-API package:
    pip install turso_serverless
Environment:
    TURSO_DATABASE_URL=https://your-database.turso.io
    TURSO_AUTH_TOKEN=your-database-token
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from pydantic import ValidationError

from gracedays.models import PurchaseSaveRequest


MANUAL_EVIDENCE_RE = re.compile(r"^Entered manually by you on \d{4}-\d{2}-\d{2}$")
PURCHASE_STATUSES = {"active", "returned", "cancelled", "resolved"}
DEADLINE_STATUSES = {"open", "completed", "dismissed"}
VERIFICATIONS = {"explicit", "derived", "user_entered"}

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS purchases (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 160),
        merchant TEXT CHECK (merchant IS NULL OR length(merchant) BETWEEN 1 AND 120),
        purchase_type TEXT NOT NULL CHECK (purchase_type IN ('physical_product','subscription','digital_purchase','other')),
        order_reference TEXT CHECK (order_reference IS NULL OR length(order_reference) <= 80),
        order_date TEXT CHECK (order_date IS NULL OR (length(order_date) = 10 AND date(order_date) = order_date)),
        delivery_date TEXT CHECK (delivery_date IS NULL OR (length(delivery_date) = 10 AND date(delivery_date) = delivery_date)),
        trial_start_date TEXT CHECK (trial_start_date IS NULL OR (length(trial_start_date) = 10 AND date(trial_start_date) = trial_start_date)),
        price_text TEXT CHECK (price_text IS NULL OR length(price_text) <= 60),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','returned','cancelled','resolved')),
        policy_summary TEXT CHECK (policy_summary IS NULL OR length(policy_summary) <= 400),
        policy_excerpt TEXT CHECK (policy_excerpt IS NULL OR length(policy_excerpt) <= 600),
        unknown_fields TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(unknown_fields)),
        source_text TEXT NOT NULL DEFAULT '' CHECK (length(source_text) <= 20000),
        source_hash TEXT CHECK (source_hash IS NULL OR (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*')),
        is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0,1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS deadlines (
        id TEXT PRIMARY KEY,
        purchase_id TEXT NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
        deadline_type TEXT NOT NULL CHECK (deadline_type IN ('return_by','trial_cancel_by','renewal_on','warranty_expires','other')),
        due_date TEXT NOT NULL CHECK (length(due_date) = 10 AND date(due_date) = due_date),
        rule_text TEXT NOT NULL CHECK (length(trim(rule_text)) BETWEEN 1 AND 300),
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','completed','dismissed')),
        verification TEXT NOT NULL CHECK (verification IN ('explicit','derived','user_entered')),
        derivation_note TEXT CHECK (derivation_note IS NULL OR length(derivation_note) <= 300),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY,
        purchase_id TEXT NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
        deadline_id TEXT REFERENCES deadlines(id) ON DELETE CASCADE,
        field_name TEXT NOT NULL CHECK (length(field_name) BETWEEN 1 AND 80),
        source_excerpt TEXT NOT NULL CHECK (length(trim(source_excerpt)) BETWEEN 1 AND 600),
        verification_status TEXT NOT NULL CHECK (verification_status IN ('explicit','derived','user_entered')),
        source_hash TEXT NOT NULL CHECK (length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS action_drafts (
        id TEXT PRIMARY KEY,
        purchase_id TEXT NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
        action_type TEXT NOT NULL CHECK (action_type IN ('return','cancellation')),
        draft_text TEXT NOT NULL CHECK (length(draft_text) BETWEEN 1 AND 12000),
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_purchases_status_created ON purchases(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_purchases_demo ON purchases(is_demo)",
    "CREATE INDEX IF NOT EXISTS idx_purchases_order_reference ON purchases(order_reference)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_purchases_unique_source_hash ON purchases(source_hash) WHERE is_demo = 0 AND source_hash IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_deadlines_purchase ON deadlines(purchase_id)",
    "CREATE INDEX IF NOT EXISTS idx_deadlines_due_status ON deadlines(due_date, status)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_purchase ON evidence(purchase_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_deadline ON evidence(deadline_id)",
    "CREATE INDEX IF NOT EXISTS idx_drafts_purchase ON action_drafts(purchase_id)",
)


class TursoDatabaseError(RuntimeError):
    """Database operation failed. `status_code` is compatible with old API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TursoConfigurationError(TursoDatabaseError):
    pass


class TursoDatabase:
    """Small CRUD repository backed directly by a remote Turso database."""

    def __init__(
        self,
        database_url: str | None = None,
        auth_token: str | None = None,
        *,
        connect_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.database_url = (database_url or os.getenv("TURSO_DATABASE_URL", "")).strip()
        self.auth_token = (auth_token or os.getenv("TURSO_AUTH_TOKEN", "")).strip()
        self._connect_factory = connect_factory
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.database_url and self.auth_token)

    def _open_connection(self):
        if not self.configured:
            raise TursoConfigurationError(
                "Turso is not configured. Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in your .env file."
            )
        factory = self._connect_factory
        if factory is None:
            try:
                import turso_serverless
            except ImportError as exc:
                raise TursoConfigurationError(
                    "The Turso driver is not installed. Run: python -m pip install turso_serverless"
                ) from exc
            factory = turso_serverless.connect
        try:
            return factory(self.database_url, auth_token=self.auth_token)
        except Exception as exc:
            raise TursoDatabaseError(f"Could not connect to Turso: {exc}") from exc

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        connection = self._open_connection()
        try:
            if not self._schema_ready:
                with self._schema_lock:
                    if not self._schema_ready:
                        self._ensure_schema(connection)
                        self._schema_ready = True
            yield connection
        except TursoDatabaseError:
            self._rollback(connection)
            raise
        except Exception as exc:
            self._rollback(connection)
            message = str(exc)
            status = 409 if "UNIQUE constraint" in message or "unique constraint" in message.lower() else None
            if status == 409:
                raise TursoDatabaseError("A purchase with this source text already exists.", status) from exc
            raise TursoDatabaseError(message) from exc
        finally:
            try:
                connection.close()
            except Exception:
                pass

    @staticmethod
    def _rollback(connection: Any) -> None:
        try:
            connection.rollback()
        except Exception:
            pass

    def _ensure_schema(self, connection: Any) -> None:
        # PRAGMA may be restricted by some remote transports; do not make it a blocker.
        try:
            connection.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()

    @staticmethod
    def _to_dict(cursor: Any, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return dict(row)
        if hasattr(row, "keys"):
            try:
                return {key: row[key] for key in row.keys()}
            except Exception:
                pass
        description = getattr(cursor, "description", None) or []
        columns = [str(column[0]) for column in description]
        return dict(zip(columns, row))

    @classmethod
    def _fetch_all(cls, connection: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = connection.execute(sql, params)
        rows = cursor.fetchall()
        result = [cls._to_dict(cursor, row) for row in rows]
        for row in result:
            if "is_demo" in row:
                row["is_demo"] = bool(row["is_demo"])
            if "unknown_fields" in row and isinstance(row["unknown_fields"], str):
                try:
                    parsed = json.loads(row["unknown_fields"])
                    row["unknown_fields"] = parsed if isinstance(parsed, list) else []
                except (TypeError, json.JSONDecodeError):
                    row["unknown_fields"] = []
        return result

    @classmethod
    def _fetch_one(cls, connection: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor = connection.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        result = cls._to_dict(cursor, row)
        if "is_demo" in result:
            result["is_demo"] = bool(result["is_demo"])
        if isinstance(result.get("unknown_fields"), str):
            try:
                parsed = json.loads(result["unknown_fields"])
                result["unknown_fields"] = parsed if isinstance(parsed, list) else []
            except (TypeError, json.JSONDecodeError):
                result["unknown_fields"] = []
        return result

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _manual_excerpt(value: str, verification: str) -> bool:
        return verification == "user_entered" and bool(MANUAL_EVIDENCE_RE.fullmatch(value))

    def _validated_payload(self, record: dict[str, Any], *, force_demo: bool = False) -> dict[str, Any]:
        try:
            payload = PurchaseSaveRequest.model_validate(record).model_dump(mode="json")
        except ValidationError as exc:
            raise TursoDatabaseError(f"Invalid purchase payload: {exc}", 400) from exc

        source_text = payload["source_text"]
        expected_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if payload["source_hash"] != expected_hash:
            raise TursoDatabaseError("source_hash does not match source_text", 400)

        deadline_ids = {item["id"] for item in payload["deadlines"]}
        for evidence in payload["evidence"]:
            excerpt = evidence["source_excerpt"]
            manual = self._manual_excerpt(excerpt, evidence["verification_status"])
            if not manual and excerpt not in source_text:
                raise TursoDatabaseError(
                    f"Evidence excerpt for '{evidence['field_name']}' is not an exact substring of source_text", 400
                )
            if evidence["source_hash"] != expected_hash:
                raise TursoDatabaseError(f"Evidence hash for '{evidence['field_name']}' does not match source_hash", 400)
            if evidence.get("deadline_id") and evidence["deadline_id"] not in deadline_ids:
                raise TursoDatabaseError("Evidence references a deadline that does not exist in this purchase", 400)

        for deadline in payload["deadlines"]:
            excerpt = deadline["evidence_excerpt"]
            manual = self._manual_excerpt(excerpt, deadline["verification"])
            if not manual and excerpt not in source_text:
                raise TursoDatabaseError(
                    f"Deadline evidence for '{deadline['deadline_type']}' is not an exact substring of source_text", 400
                )
        payload["is_demo"] = bool(force_demo or payload.get("is_demo", False))
        return payload

    def health(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "not_configured",
                "database": "turso",
                "detail": "Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in the .env file.",
            }
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1").fetchone()
            return {"status": "healthy", "database": "turso", "detail": "Connected and schema ready"}
        except Exception as exc:
            return {"status": "unavailable", "database": "turso", "detail": str(exc)[:300]}

    def list_purchases(self, query: str = "", limit: int = 50) -> dict[str, Any]:
        query = query.strip()[:100]
        limit = max(1, min(int(limit), 100))
        with self._connection() as connection:
            rows = self._fetch_all(connection, """
                SELECT * FROM purchases
                WHERE (? = '' OR lower(title) LIKE '%' || lower(?) || '%'
                    OR lower(coalesce(merchant,'')) LIKE '%' || lower(?) || '%'
                    OR lower(coalesce(order_reference,'')) LIKE '%' || lower(?) || '%')
                ORDER BY created_at DESC LIMIT ?
            """, (query, query, query, query, limit))
        return {"purchases": rows}

    def get_purchase(self, purchase_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            purchase = self._fetch_one(connection, "SELECT * FROM purchases WHERE id = ? LIMIT 1", (purchase_id,))
            if purchase is None:
                raise TursoDatabaseError("Purchase not found", 404)
            deadlines = self._fetch_all(connection, "SELECT * FROM deadlines WHERE purchase_id = ? ORDER BY due_date ASC", (purchase_id,))
            evidence = self._fetch_all(connection, "SELECT * FROM evidence WHERE purchase_id = ? ORDER BY created_at ASC", (purchase_id,))
        return {"purchase": purchase, "deadlines": deadlines, "evidence": evidence}

    def list_deadlines(self, include_closed: bool = False, limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit), 300))
        with self._connection() as connection:
            rows = self._fetch_all(connection, """
                SELECT d.*, p.title, p.merchant, p.status AS purchase_status, p.is_demo,
                    (SELECT e.source_excerpt FROM evidence e
                     WHERE e.deadline_id = d.id
                       AND e.verification_status IN ('explicit','derived','user_entered')
                     ORDER BY e.created_at ASC LIMIT 1) AS evidence_excerpt
                FROM deadlines d JOIN purchases p ON p.id = d.purchase_id
                WHERE (? = 1 OR (d.status = 'open' AND p.status = 'active'))
                ORDER BY d.due_date ASC LIMIT ?
            """, (1 if include_closed else 0, limit))
        return {"deadlines": rows}

    def update_deadline_status(self, deadline_id: str, status: str) -> dict:
        """Update only deadline status; preserve date and evidence."""
        if status not in {"open", "completed", "dismissed"}:
            raise TursoDatabaseError(
                "status must be open, completed, or dismissed", 400
            )

        if not deadline_id or len(deadline_id) > 80:
            raise TursoDatabaseError("A valid deadline_id is required", 400)

        with self._connection() as connection:
            existing = self._fetch_one(
                connection,
                "SELECT id FROM deadlines WHERE id = ? LIMIT 1",
                (deadline_id,),
            )

            if existing is None:
                raise TursoDatabaseError("Deadline not found", 404)

            connection.execute(
                "UPDATE deadlines SET status = ?, updated_at = ? WHERE id = ?",
                (status, self._now(), deadline_id),
            )
            connection.commit()

        return {
            "id": deadline_id,
            "status": status,
            "updated": True,
            "external_action_performed": False,
        }

    def update_purchase_status(self, purchase_id: str, status: str) -> dict[str, Any]:
        if status not in PURCHASE_STATUSES:
            raise TursoDatabaseError("status must be active, returned, cancelled, or resolved", 400)
        with self._connection() as connection:
            exists = self._fetch_one(connection, "SELECT id FROM purchases WHERE id = ?", (purchase_id,))
            if exists is None:
                raise TursoDatabaseError("Purchase not found", 404)
            connection.execute("UPDATE purchases SET status = ?, updated_at = ? WHERE id = ?", (status, self._now(), purchase_id))
            connection.commit()
        return {"id": purchase_id, "status": status, "updated": True}

    def delete_purchase(self, purchase_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            exists = self._fetch_one(connection, "SELECT id FROM purchases WHERE id = ?", (purchase_id,))
            if exists is None:
                raise TursoDatabaseError("Purchase not found", 404)
            # Explicitly delete dependants to work regardless of connection-level FK settings.
            connection.execute("DELETE FROM action_drafts WHERE purchase_id = ?", (purchase_id,))
            connection.execute("DELETE FROM evidence WHERE purchase_id = ?", (purchase_id,))
            connection.execute("DELETE FROM deadlines WHERE purchase_id = ?", (purchase_id,))
            connection.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
            connection.commit()
        return {"id": purchase_id, "deleted": True}

    def _insert_purchase(self, connection: Any, payload: dict[str, Any], at: str) -> None:
        connection.execute("""
            INSERT INTO purchases (
                id,title,merchant,purchase_type,order_reference,order_date,delivery_date,
                trial_start_date,price_text,status,policy_summary,policy_excerpt,unknown_fields,
                source_text,source_hash,is_demo,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            payload["id"], payload["title"].strip(), payload.get("merchant"), payload["purchase_type"],
            payload.get("order_reference"), payload.get("order_date"), payload.get("delivery_date"),
            payload.get("trial_start_date"), payload.get("price_text"), payload.get("status", "active"),
            payload.get("policy_summary"), payload.get("policy_excerpt"), json.dumps(payload.get("unknown_fields", [])),
            payload.get("source_text", ""), payload["source_hash"], 1 if payload.get("is_demo") else 0, at, at,
        ))
        for deadline in payload.get("deadlines", []):
            connection.execute("""
                INSERT INTO deadlines (id,purchase_id,deadline_type,due_date,rule_text,status,verification,derivation_note,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                deadline["id"], payload["id"], deadline["deadline_type"], deadline["due_date"], deadline["rule_text"],
                deadline.get("status", "open"), deadline["verification"], deadline.get("derivation_note"), at, at,
            ))
        for item in payload.get("evidence", []):
            connection.execute("""
                INSERT INTO evidence (id,purchase_id,deadline_id,field_name,source_excerpt,verification_status,source_hash,created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                item["id"], payload["id"], item.get("deadline_id"), item["field_name"], item["source_excerpt"],
                item["verification_status"], item["source_hash"], at,
            ))

    def save_purchase(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = self._validated_payload(record)
        if payload["is_demo"]:
            raise TursoDatabaseError("Demo records can only be created through seed_demo_data", 400)
        with self._connection() as connection:
            duplicate = self._fetch_one(
                connection,
                "SELECT id FROM purchases WHERE is_demo = 0 AND source_hash = ? LIMIT 1",
                (payload["source_hash"],),
            )
            if duplicate:
                raise TursoDatabaseError(f"Duplicate purchase already exists: {duplicate['id']}", 409)
            at = self._now()
            self._insert_purchase(connection, payload, at)
            connection.commit()
        return {"id": payload["id"], "message": "Purchase saved"}

    def seed_demo(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(records, list) or len(records) > 20:
            raise TursoDatabaseError("Demo purchases must be a list containing at most 20 records", 400)
        payloads = [self._validated_payload(record, force_demo=True) for record in records]
        with self._connection() as connection:
            at = self._now()
            # Replace demo records in the same transaction; normal user records are untouched.
            connection.execute("DELETE FROM purchases WHERE is_demo = 1")
            for payload in payloads:
                self._insert_purchase(connection, payload, at)
            connection.commit()
        return {"seeded": len(payloads), "replaced_demo_records": True}

    def reset_demo(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = self._fetch_all(connection, "SELECT id FROM purchases WHERE is_demo = 1")
            ids = [row["id"] for row in rows]
            for purchase_id in ids:
                connection.execute("DELETE FROM action_drafts WHERE purchase_id = ?", (purchase_id,))
                connection.execute("DELETE FROM evidence WHERE purchase_id = ?", (purchase_id,))
                connection.execute("DELETE FROM deadlines WHERE purchase_id = ?", (purchase_id,))
            connection.execute("DELETE FROM purchases WHERE is_demo = 1")
            connection.commit()
        return {"deleted_demo_records": len(ids), "non_demo_records_untouched": True}
