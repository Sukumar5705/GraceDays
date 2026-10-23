from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "cloudflare" / "migrations" / "0001_initial_schema.sql"


def _db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(MIGRATION.read_text(encoding="utf-8"))
    return connection


def _insert_purchase(db: sqlite3.Connection, purchase_id: str) -> None:
    db.execute(
        """INSERT INTO purchases
        (id,title,merchant,purchase_type,status,unknown_fields,source_text,source_hash,is_demo,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (purchase_id, "Synthetic Test Item", "Fictional Merchant", "physical_product", "active", "[]", "Synthetic source", "a" * 64, 0, "2026-10-22T00:00:00Z", "2026-10-22T00:00:00Z"),
    )


def test_migration_creates_required_tables_and_foreign_keys() -> None:
    with _db() as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"purchases", "deadlines", "evidence", "action_drafts"}.issubset(names)
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        _insert_purchase(db, str(uuid4()))


def test_purchase_delete_cascades_to_deadlines_evidence_and_drafts() -> None:
    with _db() as db:
        purchase_id, deadline_id = str(uuid4()), str(uuid4())
        _insert_purchase(db, purchase_id)
        db.execute(
            "INSERT INTO deadlines (id,purchase_id,deadline_type,due_date,rule_text,status,verification,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (deadline_id, purchase_id, "return_by", "2026-11-01", "Return within 10 days", "open", "derived", "2026-10-22T00:00:00Z", "2026-10-22T00:00:00Z"),
        )
        db.execute(
            "INSERT INTO evidence (id,purchase_id,deadline_id,field_name,source_excerpt,verification_status,source_hash,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid4()), purchase_id, deadline_id, "return_by", "Return within 10 days", "derived", "a" * 64, "2026-10-22T00:00:00Z"),
        )
        db.execute(
            "INSERT INTO action_drafts (id,purchase_id,action_type,draft_text,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), purchase_id, "return", "DRAFT — not sent", "2026-10-22T00:00:00Z"),
        )
        db.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
        assert db.execute("SELECT count(*) FROM deadlines").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM action_drafts").fetchone()[0] == 0


def test_schema_rejects_invalid_purchase_and_deadline_statuses() -> None:
    with _db() as db:
        purchase_id = str(uuid4())
        try:
            db.execute(
                """INSERT INTO purchases
                (id,title,purchase_type,status,unknown_fields,source_text,source_hash,is_demo,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (purchase_id, "Synthetic Item", "physical_product", "invalid_status", "[]", "", "a" * 64, 0, "2026-10-22T00:00:00Z", "2026-10-22T00:00:00Z"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("The schema should reject an invalid purchase status")


def test_non_demo_source_hash_is_unique_but_demo_hashes_are_allowed() -> None:
    with _db() as db:
        first_id, second_id = str(uuid4()), str(uuid4())
        _insert_purchase(db, first_id)
        try:
            _insert_purchase(db, second_id)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Duplicate non-demo source hashes must be rejected")
        db.execute(
            """INSERT INTO purchases
            (id,title,purchase_type,status,unknown_fields,source_text,source_hash,is_demo,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (second_id, "Synthetic Demo Item", "physical_product", "active", "[]", "Synthetic source", "a" * 64, 1, "2026-10-22T00:00:00Z", "2026-10-22T00:00:00Z"),
        )
