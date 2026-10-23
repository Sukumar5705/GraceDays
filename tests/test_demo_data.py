from __future__ import annotations

from gracedays.config import Settings
from gracedays.evidence import source_hash
from gracedays.services.demo import build_demo_records


def test_demo_records_are_synthetic_relative_to_clock_and_evidence_is_grounded() -> None:
    settings = Settings(fake_today="2026-11-09")
    records = build_demo_records(settings)
    assert len(records) == 3
    assert all(record["is_demo"] is True for record in records)
    assert all(record["source_hash"] == source_hash(record["source_text"]) for record in records)
    for record in records:
        assert record["order_date"] is not None
        assert record["delivery_date"] is not None
        for item in record["evidence"]:
            if item["verification_status"] != "user_entered":
                assert item["source_excerpt"] in record["source_text"]
            assert item["source_hash"] == record["source_hash"]
        for deadline in record["deadlines"]:
            assert deadline["evidence_excerpt"] in record["source_text"]
            assert len(deadline["due_date"]) == 10
