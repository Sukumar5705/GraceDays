from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from gracedays.config import Settings
from gracedays.date_engine import compute_rule
from gracedays.evidence import source_hash


def _display_date(value: date) -> str:
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def build_demo_records(settings: Settings) -> list[dict[str, Any]]:
    path = settings.repository_root() / "data" / "demo_purchases.json"
    templates = json.loads(path.read_text(encoding="utf-8"))
    from gracedays.clock import Clock
    today = Clock(settings.timezone, settings.fake_today).today()
    records = []
    for item in templates:
        order_day = today - timedelta(days=int(item["order_days_ago"]))
        delivery_day = today - timedelta(days=int(item["delivery_days_ago"]))
        anchor_field = item.get("anchor_field", "delivery_date")
        anchor_day = order_day if anchor_field == "order_date" else delivery_day
        if anchor_field == "trial_start_date":
            anchor_day = order_day
        deadline_day = compute_rule(anchor_day, int(item["window_days"]), "days")
        title = item["title"]
        merchant = item["merchant"]
        reference = f"DEMO-{uuid4().hex[:8].upper()}"
        delivery_line = f"Your {title} was delivered on {_display_date(delivery_day)}."
        order_line = f"Order date: {_display_date(order_day)}. Order number: {reference}."
        anchor_phrase = item.get("anchor_phrase", "delivery")
        rule_line = f"{item['policy_prefix']} {item['window_days']} days of {anchor_phrase}."
        trial_line = f"Trial started on {_display_date(anchor_day)}." if anchor_field == "trial_start_date" else None
        source = "\n".join(part for part in (order_line, delivery_line, trial_line, rule_line) if part)
        digest = source_hash(source)
        deadline_id = str(uuid4())
        purchase_id = str(uuid4())
        evidence = [
            {"id": str(uuid4()), "deadline_id": None, "field_name": "title", "source_excerpt": delivery_line, "verification_status": "explicit", "source_hash": digest},
            {"id": str(uuid4()), "deadline_id": None, "field_name": "merchant", "source_excerpt": f"Merchant: {merchant}.", "verification_status": "user_entered", "source_hash": digest},
            {"id": str(uuid4()), "deadline_id": deadline_id, "field_name": f"deadline:{item['deadline_type']}", "source_excerpt": rule_line, "verification_status": "derived", "source_hash": digest},
        ]
        source = source + f"\nMerchant: {merchant}."
        # Re-hash once source is finalized; evidence references the same sanitized source.
        digest = source_hash(source)
        for ev in evidence:
            ev["source_hash"] = digest
        records.append({
            "id": purchase_id,
            "title": title,
            "merchant": merchant,
            "purchase_type": item.get("purchase_type", "physical_product"),
            "order_reference": reference,
            "order_date": order_day.isoformat(),
            "delivery_date": delivery_day.isoformat(),
            "trial_start_date": anchor_day.isoformat() if anchor_field == "trial_start_date" else None,
            "price_text": item.get("price_text"),
            "status": "active",
            "policy_summary": rule_line,
            "policy_excerpt": rule_line,
            "unknown_fields": [],
            "source_text": source,
            "source_hash": digest,
            "is_demo": True,
            "deadlines": [{
                "id": deadline_id,
                "deadline_type": item["deadline_type"],
                "due_date": deadline_day.isoformat(),
                "rule_text": rule_line,
                "status": "open",
                "evidence_excerpt": rule_line,
                "verification": "derived",
                "derivation_note": f"{anchor_field.replace('_', ' ').title()} {anchor_day.isoformat()} + {item['window_days']} days (anchor day counted as day 0).",
            }],
            "evidence": evidence,
        })
    return records
