from __future__ import annotations

import re
from typing import Any


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def find_duplicates(candidate: dict[str, Any], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conservative duplicate warning: exact order reference, or title+merchant+date."""
    matches = []
    title = _norm(candidate.get("title"))
    merchant = _norm(candidate.get("merchant"))
    reference = _norm(candidate.get("order_reference"))
    order_date = candidate.get("order_date")
    for purchase in existing:
        same_ref = bool(reference) and reference == _norm(purchase.get("order_reference"))
        same_identity = title and title == _norm(purchase.get("title")) and merchant == _norm(purchase.get("merchant"))
        same_date = order_date and order_date == purchase.get("order_date")
        if same_ref or (same_identity and (same_date or not order_date)):
            matches.append({"id": purchase.get("id"), "title": purchase.get("title"), "merchant": purchase.get("merchant"), "order_date": purchase.get("order_date"), "reason": "Matching order reference" if same_ref else "Matching title, merchant and order date"})
    return matches
