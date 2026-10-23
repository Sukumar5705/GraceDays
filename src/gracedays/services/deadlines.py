from __future__ import annotations

from datetime import date
from typing import Any

from gracedays.clock import Clock

ACTIONABLE = {"return_by", "trial_cancel_by", "other"}
INFORMATIONAL = {"renewal_on", "warranty_expires"}


def derive_state(deadline: dict[str, Any], purchase_status: str, today: date) -> str:
    status = deadline.get("status", "open")
    if status == "completed":
        return "completed"
    if status == "dismissed":
        return "dismissed"
    if purchase_status != "active":
        return "closed"
    due = date.fromisoformat(str(deadline["due_date"]))
    if due == today:
        return "due_today"
    if due > today:
        return "upcoming"
    return "overdue" if deadline.get("deadline_type") in ACTIONABLE else "passed"


def decorate_deadlines(rows: list[dict[str, Any]], clock: Clock, within_days: int = 7, include_closed: bool = False) -> list[dict[str, Any]]:
    today = clock.today()
    result = []
    for raw in rows:
        row = dict(raw)
        row["derived_state"] = derive_state(row, row.get("purchase_status", "active"), today)
        row["days_remaining"] = (date.fromisoformat(row["due_date"]) - today).days
        row["as_of_date"] = today.isoformat()
        row["timezone"] = clock.timezone_name
        if not include_closed:
            if row["derived_state"] not in {"overdue", "due_today", "upcoming"}:
                continue
            if row["days_remaining"] > within_days:
                continue
        result.append(row)

    rank = {"overdue": 0, "due_today": 1, "upcoming": 2, "passed": 3, "closed": 4, "completed": 5, "dismissed": 6}
    result.sort(key=lambda row: (rank.get(row["derived_state"], 9), row.get("due_date", "")))
    return result
