from __future__ import annotations

from datetime import date
from typing import Any

from gracedays.services.deadlines import derive_state


def draft_action_message(purchase: dict[str, Any], action_type: str, today: date) -> dict[str, str]:
    if action_type not in {"return", "cancellation"}:
        raise ValueError("action_type must be 'return' or 'cancellation'")
    title = str(purchase.get("title") or "[product name]")
    merchant = str(purchase.get("merchant") or "[merchant name]")
    order_ref = str(purchase.get("order_reference") or "[order reference]")
    deadlines = purchase.get("deadlines", []) or []
    expected_type = "return_by" if action_type == "return" else "trial_cancel_by"
    matching = next((d for d in deadlines if d.get("deadline_type") == expected_type), None)
    if matching:
        due = str(matching.get("due_date", "[deadline date]"))
        state = derive_state(matching, str(purchase.get("status", "active")), today)
        window_line = (
            f"The saved {expected_type.replace('_', ' ')} is {due}. It appears to be past; please check the seller's current policy before proceeding."
            if state == "overdue" else f"The saved {expected_type.replace('_', ' ')} is {due}. Please verify the seller's policy before proceeding."
        )
    else:
        window_line = "I could not find a verified deadline in the saved record, so please confirm the current policy with the merchant."
    if action_type == "return":
        subject = f"Return request for {title} — order {order_ref}"
        body = (
            f"Hello {merchant},\n\nI would like to ask about returning {title} under order {order_ref}.\n"
            f"{window_line}\n\nPlease let me know the appropriate next steps and any information you need.\n\nThank you."
        )
    else:
        subject = f"Cancellation request — {title} / order {order_ref}"
        body = (
            f"Hello {merchant},\n\nPlease explain how I can cancel the trial or subscription associated with {title} (reference {order_ref}).\n"
            f"{window_line}\n\nPlease confirm the cancellation requirements and effective date.\n\nThank you."
        )
    return {"notice": "DRAFT — NOT SENT", "subject": subject, "draft_text": body, "external_action_performed": "false"}
