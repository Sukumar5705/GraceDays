from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from gracedays.models import CandidateDeadline, CandidateEvidence, ExtractionCandidate, PurchaseType
from gracedays.providers.base import AgentTurn, ToolCall
from gracedays.date_engine import parse_relative_rule

_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE_PATTERNS = [
    re.compile(rf"\b{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}\b", re.I),
    re.compile(rf"\b\d{{1,2}}\s+{_MONTH}\s+\d{{4}}\b", re.I),
    re.compile(r"\b(?:19|20|21)\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}/(?:19|20|21)\d{2}\b"),
]
_PRICE_RE = re.compile(r"(?:\$|USD\s*|INR\s*|₹\s*|€\s*|£\s*)\s?\d+(?:[.,]\d{1,2})?(?:\s*/\s*(?:month|year|week))?", re.I)


def _sentences(text: str) -> list[str]:
    # Keeping delimiters in sentence boundaries is unnecessary for verification;
    # source excerpts are sliced from the original source, not reconstructed.
    spans = re.finditer(r"[^\n.!?]+(?:[.!?]+|$)|[^\n]+", text)
    result = []
    for match in spans:
        snippet = match.group(0).strip()
        if snippet and snippet not in result:
            result.append(snippet)
    return result


def _sentence_for(text: str, position: int) -> str:
    start = max(text.rfind("\n", 0, position), text.rfind(". ", 0, position), text.rfind("! ", 0, position), text.rfind("? ", 0, position))
    start = 0 if start < 0 else start + (1 if text[start:start + 1] == "\n" else 2)
    candidates = [i for i in (text.find("\n", position), text.find(". ", position), text.find("! ", position), text.find("? ", position)) if i >= 0]
    end = min(candidates) + (0 if min(candidates) < len(text) and text[min(candidates):min(candidates)+1] == "\n" else 1) if candidates else len(text)
    return text[start:end].strip()


def _date_match(text: str):
    matches = []
    for pattern in _DATE_PATTERNS:
        matches.extend(pattern.finditer(text))
    return sorted(matches, key=lambda item: item.start())


def _find_date(sentence: str) -> str | None:
    matches = _date_match(sentence)
    return matches[0].group(0) if matches else None


def _infer_title(text: str) -> tuple[str, str | None]:
    patterns = [
        re.compile(r"(?:product|item|purchase)\s*:\s*([^\n,;.]+)", re.I),
        re.compile(r"order confirmation for\s+([^\n,.]+)", re.I),
        re.compile(r"your\s+([^\n,.]+?)\s+(?:was delivered|was shipped|has shipped|order was placed|order is confirmed)", re.I),
        re.compile(r"thank you for ordering\s+([^\n,.]+)", re.I),
        re.compile(r"order for\s+([^\n,.]+?)\s+(?:was placed|is confirmed)", re.I),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            title = match.group(1).strip().strip('"\'')[:160]
            return title, _sentence_for(text, match.start())
    first_sentence = next((s.strip() for s in _sentences(text) if s.strip()), "")
    return "Unknown purchase", first_sentence or None


def _infer_merchant(text: str) -> tuple[str | None, str | None]:
    patterns = [
        re.compile(r"\b(?:merchant|seller|store)\s*:\s*([^\n,;.]+)", re.I),
        re.compile(r"\bfrom\s+([A-Z][A-Za-z0-9&' -]{1,50}?)(?=\s+(?:receipt|order|on|for|has|sent)|[.,\n]|$)"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()[:120]
            return value, _sentence_for(text, match.start())
    return None, None


def _infer_type(text: str) -> PurchaseType:
    lower = text.lower()
    if any(token in lower for token in ("subscription", "free trial", "trial starts", "monthly plan", "billing cycle", "renews on")):
        return PurchaseType.SUBSCRIPTION
    if any(token in lower for token in ("download", "digital edition", "license key", "software license")):
        return PurchaseType.DIGITAL_PURCHASE
    return PurchaseType.PHYSICAL_PRODUCT


def _find_context_date(text: str, key_patterns: tuple[str, ...]) -> tuple[str | None, str | None]:
    for sentence in _sentences(text):
        if any(re.search(pattern, sentence, re.I) for pattern in key_patterns):
            date_text = _find_date(sentence)
            if date_text:
                return date_text, sentence
    return None, None


def _deadline_kind(sentence: str) -> str | None:
    lower = sentence.lower()
    if "warranty" in lower:
        return "warranty_expires"
    if "renew" in lower or "billing date" in lower or "next payment" in lower:
        return "renewal_on"
    if "trial" in lower or ("cancel" in lower and "subscription" in lower):
        return "trial_cancel_by"
    if "return" in lower or "refund" in lower:
        return "return_by"
    return None


def _explicit_due_date(sentence: str, deadline_type: str) -> str | None:
    lower = sentence.lower()
    positive = {
        "return_by": r"(?:return|refund).{0,45}(?:by|before|until|through|no later than)",
        "trial_cancel_by": r"(?:cancel|cancellation|trial ends?|trial expires?).{0,45}(?:by|before|on|until|expires?)",
        "renewal_on": r"(?:renews?|renewal|billing date|next payment).{0,45}(?:on|is|date:?)",
        "warranty_expires": r"warranty.{0,45}(?:expires?|ends?|until|through|on)",
    }
    if deadline_type in positive and not re.search(positive[deadline_type], lower):
        return None
    return _find_date(sentence)


class MockProvider:
    """Deterministic, visibly offline provider; no remote calls or fabricated dates."""

    name = "mock"

    def extract(self, source_text: str) -> ExtractionCandidate:
        title, title_evidence = _infer_title(source_text)
        merchant, merchant_evidence = _infer_merchant(source_text)
        order_date_text, order_evidence = _find_context_date(source_text, (r"\border(?:ed| date| was placed| confirmation)\b", r"\bpurchased on\b"))
        delivery_date_text, delivery_evidence = _find_context_date(source_text, (r"\bdeliver(?:ed|y date|y on|y is)\b", r"\barrived on\b"))
        trial_start_text, trial_evidence = _find_context_date(source_text, (r"\btrial (?:starts?|begins?|started|began)\b", r"\bactivated on\b"))
        price_match = _PRICE_RE.search(source_text)
        price_text = price_match.group(0).strip() if price_match else None
        price_evidence = _sentence_for(source_text, price_match.start()) if price_match else None

        fields = []
        for name, excerpt in [
            ("title", title_evidence), ("merchant", merchant_evidence),
            ("order_date", order_evidence), ("delivery_date", delivery_evidence),
            ("trial_start_date", trial_evidence), ("price_text", price_evidence),
        ]:
            if excerpt:
                fields.append(CandidateEvidence(field_name=name, source_excerpt=excerpt))

        deadlines: list[CandidateDeadline] = []
        unknown: list[str] = []
        policy_sentence = None
        for sentence in _sentences(source_text):
            kind = _deadline_kind(sentence)
            if not kind:
                continue
            policy_sentence = policy_sentence or sentence
            rule = parse_relative_rule(sentence)
            if rule:
                deadlines.append(CandidateDeadline(
                    deadline_type=kind,
                    date_text=None,
                    evidence_excerpt=sentence,
                    rule_text=rule.phrase,
                    rule_anchor=rule.anchor,
                    amount=rule.amount,
                    unit=rule.unit,
                ))
                continue
            explicit_date = _explicit_due_date(sentence, kind)
            if explicit_date:
                deadlines.append(CandidateDeadline(
                    deadline_type=kind,
                    date_text=explicit_date,
                    evidence_excerpt=sentence,
                    rule_text=sentence[:300],
                ))
            else:
                unknown.append(kind)
            if len(deadlines) >= 5:
                break

        if not deadlines and any(token in source_text.lower() for token in ("return window", "return policy", "free trial", "warranty", "renewal")):
            possible = "trial_cancel_by" if "trial" in source_text.lower() else "warranty_expires" if "warranty" in source_text.lower() else "renewal_on" if "renew" in source_text.lower() else "return_by"
            unknown.append(possible)

        policy_excerpt = policy_sentence[:600] if policy_sentence else None
        if policy_excerpt:
            fields.append(CandidateEvidence(field_name="policy_excerpt", source_excerpt=policy_excerpt))
        if title == "Unknown purchase":
            unknown.append("title")
        return ExtractionCandidate(
            title=title,
            merchant=merchant,
            purchase_type=_infer_type(source_text),
            order_reference=self._order_reference(source_text),
            order_date_text=order_date_text,
            delivery_date_text=delivery_date_text,
            trial_start_date_text=trial_start_text,
            price_text=price_text,
            policy_summary=policy_excerpt,
            policy_excerpt=policy_excerpt,
            field_evidence=fields,
            deadlines=deadlines[:5],
            unknown_fields=sorted(set(unknown)),
        )

    @staticmethod
    def _order_reference(text: str) -> str | None:
        match = re.search(r"\b(?:order\s*(?:number|no\.?|#)|order id)\s*[:#-]?\s*([A-Z0-9-]{4,80})", text, re.I)
        return match.group(1)[:80] if match else None

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AgentTurn:
        user_message = next((str(msg.get("content", "")) for msg in reversed(messages) if msg.get("role") == "user"), "")
        lower = user_message.lower()
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        parsed_tools: list[tuple[str, Any]] = []
        for item in tool_messages:
            try:
                parsed_tools.append((str(item.get("name", "")), json.loads(str(item.get("content", "null")))))
            except json.JSONDecodeError:
                continue

        tool_names = {tool.get("function", {}).get("name") for tool in tools}

        def call(name: str, arguments: dict[str, Any]) -> AgentTurn:
            return AgentTurn(tool_calls=[ToolCall(id=f"mock_{uuid4().hex[:10]}", name=name, arguments=arguments)])

        if any(word in lower for word in ("attention", "this week", "upcoming", "overdue", "deadline")) and "list_deadlines" in tool_names:
            if not any(name == "list_deadlines" for name, _ in parsed_tools):
                return call("list_deadlines", {"within_days": 7, "include_closed": False})
            value = next((data for name, data in reversed(parsed_tools) if name == "list_deadlines"), {})
            rows = value.get("deadlines", []) if isinstance(value, dict) else []
            if not rows:
                return AgentTurn(content="There are no saved deadlines needing attention in the selected window.")
            lines = []
            for row in rows[:5]:
                title = row.get("title") or row.get("purchase_title") or "Purchase"
                due = row.get("due_date", "date unavailable")
                state = row.get("derived_state", row.get("state", "open"))
                lines.append(f"{title}: {row.get('deadline_type', 'deadline')} on {due} ({state}).")
            return AgentTurn(content="Here are the saved deadlines that need attention: " + " ".join(lines))

        action_status = None
        if any(word in lower for word in ("mark", "set", "update")) and "resolved" in lower:
            action_status = "resolved"
        elif any(word in lower for word in ("mark", "set", "update")) and "returned" in lower:
            action_status = "returned"
        elif any(word in lower for word in ("mark", "set", "update")) and "cancelled" in lower:
            action_status = "cancelled"

        wants_draft = any(token in lower for token in ("draft", "write a message", "write an email", "help me return", "help me cancel"))
        action_type = "cancellation" if ("cancel" in lower or "trial" in lower) else "return"
        already_listed = [(name, data) for name, data in parsed_tools if name == "list_purchases"]
        purchase_rows = []
        if already_listed:
            data = already_listed[-1][1]
            if isinstance(data, dict):
                purchase_rows = data.get("purchases", [])
        query_text = self._query_target(user_message)
        if not already_listed and "list_purchases" in tool_names:
            return call("list_purchases", {"query": query_text, "limit": 20})
        if already_listed:
            matches = purchase_rows
            if not matches:
                return AgentTurn(content="I couldn't find a matching saved purchase. Try its exact product name or add it first.")
            if len(matches) > 1:
                names = ", ".join(str(row.get("title", "Untitled")) for row in matches[:5])
                return AgentTurn(content=f"I found multiple matching purchases ({names}). Please specify which one you mean.")
            purchase = matches[0]
            purchase_id = str(purchase.get("id", ""))
            if action_status and "update_purchase_status" in tool_names and not any(name == "update_purchase_status" for name, _ in parsed_tools):
                return call("update_purchase_status", {"purchase_id": purchase_id, "status": action_status})
            detail_rows = [(name, data) for name, data in parsed_tools if name == "get_purchase_details"]
            if not detail_rows and "get_purchase_details" in tool_names:
                return call("get_purchase_details", {"purchase_id": purchase_id})
            if detail_rows:
                detail = detail_rows[-1][1]
                if action_status:
                    status_rows = [(name, data) for name, data in parsed_tools if name == "update_purchase_status"]
                    if status_rows:
                        status_val = status_rows[-1][1]
                        return AgentTurn(content=f"The saved status for {purchase.get('title', 'the purchase')} is now {status_val.get('status', action_status)}. No external return or cancellation was performed.")
                if wants_draft and "draft_action_message" in tool_names and not any(name == "draft_action_message" for name, _ in parsed_tools):
                    return call("draft_action_message", {"purchase_id": purchase_id, "action_type": action_type})
                if any(name == "draft_action_message" for name, _ in parsed_tools):
                    result = next(data for name, data in reversed(parsed_tools) if name == "draft_action_message")
                    return AgentTurn(content=f"{result.get('notice', 'DRAFT — not sent')}\n\n{result.get('draft_text', '')}")
                if isinstance(detail, dict):
                    deadlines = detail.get("deadlines", [])
                    headline = f"{detail.get('title', purchase.get('title', 'This purchase'))} is saved with status {detail.get('status', purchase.get('status', 'active'))}."
                    if deadlines:
                        first = deadlines[0]
                        return AgentTurn(content=f"{headline} Its {first.get('deadline_type', 'deadline')} is {first.get('due_date', 'not recorded')}; state: {first.get('derived_state', 'open')}. Check the evidence shown with the saved record.")
                    return AgentTurn(content=headline + " No dated deadline is currently saved for it.")
        if "list_purchases" in tool_names:
            return call("list_purchases", {"query": "", "limit": 20})
        return AgentTurn(content="I can answer from saved purchase records, draft a message, or update one purchase status. Please try a specific request.")

    @staticmethod
    def _query_target(message: str) -> str:
        quoted = re.search(r"['\"]([^'\"]{2,80})['\"]", message)
        if quoted:
            return quoted.group(1)
        match = re.search(r"(?:about|for|return|cancel|resolve|mark|details for|my)\s+(?:the\s+)?([A-Za-z0-9][A-Za-z0-9 -]{1,50}?)(?:\?|\.|\s+(?:as|by|before|please|now)\b|$)", message, re.I)
        return match.group(1).strip() if match else message[:60].strip()
