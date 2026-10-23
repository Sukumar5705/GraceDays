from __future__ import annotations

from datetime import date
import re
from typing import Any

from pydantic import ValidationError

from gracedays.config import Settings
from gracedays.date_engine import compute_rule, parse_explicit_date, parse_relative_rule
from gracedays.evidence import source_hash, verify_excerpt
from gracedays.models import (
    EvidenceReview,
    ProposedDeadline,
    ReviewPurchase,
    VerificationStatus,
)
from gracedays.providers.base import LLMProvider
from gracedays.redact import redact_card_numbers


class ExtractionError(ValueError):
    pass


def _field_evidence_matches(field_name: str, field_value: str | None, excerpt: str, source_text: str) -> bool:
    if not verify_excerpt(source_text, excerpt):
        return False
    if not field_value:
        return field_name == "policy_excerpt" or field_name == "policy_summary"
    if field_name == "policy_excerpt":
        return field_value in excerpt or excerpt in source_text
    if field_name == "order_date":
        return field_value in excerpt and bool(re.search(r"\border(?:ed| date| was placed| confirmation)\b|\bpurchased on\b", excerpt, re.I))
    if field_name == "delivery_date":
        return field_value in excerpt and bool(re.search(r"\bdeliver(?:ed|y date|y on|y is)\b|\barrived on\b", excerpt, re.I))
    if field_name == "trial_start_date":
        return field_value in excerpt and bool(re.search(r"\btrial (?:starts?|begins?|started|began)\b|\bactivated on\b", excerpt, re.I))
    return field_value.casefold() in excerpt.casefold()


def _deadline_evidence_is_relevant(kind: str, excerpt: str, date_text: str | None = None) -> bool:
    if date_text and date_text not in excerpt:
        return False
    segments = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", excerpt) if part.strip()]
    for segment in segments:
        if date_text and date_text not in segment:
            continue
        rule = parse_relative_rule(segment)
        lower = segment.lower()
        if kind == "return_by" and re.search(r"\b(return|returns|returned|refund|refunded)\b", lower) and (rule is not None or re.search(r"\b(by|before|until|through|within|no later than)\b", lower)):
            return True
        if kind == "trial_cancel_by" and ("trial" in lower or "subscription" in lower) and (rule is not None or re.search(r"\b(cancel|cancellation|by|before|until|within|expires?|ends?)\b", lower)):
            return True
        if kind == "renewal_on" and re.search(r"\b(renew|renews|renewal|billing date|next payment)\b", lower) and (rule is not None or re.search(r"\b(on|is|date|due|scheduled)\b", lower)):
            return True
        if kind == "warranty_expires" and "warranty" in lower and (rule is not None or re.search(r"\b(expires?|ends?|valid|through|until)\b", lower)):
            return True
        if kind == "other" and (rule is not None or date_text and date_text in segment):
            return True
    return False


class ExtractionService:
    def __init__(self, provider: LLMProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    def extract(self, raw_text: str) -> tuple[ReviewPurchase, dict[str, Any]]:
        if not raw_text or not raw_text.strip():
            raise ExtractionError("Paste an order email or policy text first.")
        if len(raw_text) > self.settings.max_source_text_chars:
            raise ExtractionError(f"Source text exceeds the {self.settings.max_source_text_chars:,}-character limit.")
        safe_source, redacted_count = redact_card_numbers(raw_text)
        digest = source_hash(safe_source)
        try:
            candidate = self.provider.extract(safe_source)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            raise ExtractionError(f"The extraction result could not be validated: {exc}") from exc
        except Exception as exc:  # provider/network failures should be recoverable in the UI
            raise ExtractionError(f"Extraction provider failed: {exc}") from exc

        unknown_fields = set(candidate.unknown_fields)
        candidate_field_values = {
            "title": candidate.title,
            "merchant": candidate.merchant,
            "order_date": candidate.order_date_text,
            "delivery_date": candidate.delivery_date_text,
            "trial_start_date": candidate.trial_start_date_text,
            "price_text": candidate.price_text,
            "policy_summary": candidate.policy_summary,
            "policy_excerpt": candidate.policy_excerpt,
        }
        verified_evidence: list[EvidenceReview] = []
        verified_field_names: set[str] = set()
        for item in candidate.field_evidence:
            is_verified = _field_evidence_matches(item.field_name, candidate_field_values.get(item.field_name), item.source_excerpt, safe_source)
            status = VerificationStatus.EXPLICIT if is_verified else VerificationStatus.UNVERIFIED
            verified_evidence.append(EvidenceReview(
                field_name=item.field_name,
                source_excerpt=item.source_excerpt,
                verification_status=status,
                source_hash=digest,
            ))
            if is_verified:
                verified_field_names.add(item.field_name)
            else:
                unknown_fields.add(item.field_name)

        # A summary identical to the verified policy excerpt can reuse that exact quote.
        # Do not synthesize evidence for summaries that paraphrase or differ from the source.
        if (
            candidate.policy_summary
            and candidate.policy_summary == candidate.policy_excerpt
            and "policy_summary" not in verified_field_names
        ):
            quote = next((e.source_excerpt for e in verified_evidence if e.field_name == "policy_excerpt" and e.verification_status == VerificationStatus.EXPLICIT), None)
            if quote:
                verified_evidence.append(EvidenceReview(
                    field_name="policy_summary",
                    source_excerpt=quote,
                    verification_status=VerificationStatus.EXPLICIT,
                    source_hash=digest,
                ))
                verified_field_names.add("policy_summary")

        for field_name, field_value in candidate_field_values.items():
            evidence_key = "policy_excerpt" if field_name == "policy_summary" and candidate.policy_summary == candidate.policy_excerpt else field_name
            if field_value and evidence_key not in verified_field_names:
                unknown_fields.add(field_name)

        parsed_anchors: dict[str, str | None] = {}
        date_texts = {
            "order_date": candidate.order_date_text,
            "delivery_date": candidate.delivery_date_text,
            "trial_start_date": candidate.trial_start_date_text,
        }
        field_evidence = {name: [e.source_excerpt for e in verified_evidence if e.field_name == name and e.verification_status == VerificationStatus.EXPLICIT] for name in date_texts}
        for key, date_text in date_texts.items():
            matching_quote = bool(date_text) and any(date_text in quote for quote in field_evidence[key])
            if not date_text:
                parsed_anchors[key] = None
                # Mark only contextually relevant missing anchors; do not force trial dates for a non-trial product.
                if key == "order_date" or (key == "delivery_date" and ("delivery" in safe_source.lower() or "return" in safe_source.lower())) or (key == "trial_start_date" and ("trial" in safe_source.lower() or "activation" in safe_source.lower())):
                    unknown_fields.add(key)
                continue
            if not matching_quote:
                parsed_anchors[key] = None
                unknown_fields.add(key)
                continue
            parsed = parse_explicit_date(date_text)
            parsed_anchors[key] = parsed.value.isoformat() if parsed.status == "explicit" and parsed.value else None
            if parsed.status != "explicit":
                unknown_fields.add(key)

        deadline_proposals: list[ProposedDeadline] = []
        for item in candidate.deadlines[:5]:
            evidence_ok = verify_excerpt(safe_source, item.evidence_excerpt) and _deadline_evidence_is_relevant(
                item.deadline_type.value, item.evidence_excerpt, item.date_text,
            )
            if not evidence_ok:
                deadline_proposals.append(ProposedDeadline(
                    deadline_type=item.deadline_type,
                    due_date=None,
                    rule_text=(item.rule_text or "Evidence requires review")[:300],
                    evidence_excerpt=item.evidence_excerpt[:500] or "[missing evidence]",
                    verification=VerificationStatus.UNVERIFIED,
                    needs_review=True,
                    review_reason="The proposed evidence does not occur verbatim in the source text.",
                ))
                unknown_fields.add(item.deadline_type.value)
                continue

            if item.date_text:
                # Evidence must contain the verbatim date, not merely a related policy sentence.
                if item.date_text not in item.evidence_excerpt:
                    parsed = None
                    reason = "The date text is not present in its evidence excerpt."
                else:
                    parsed = parse_explicit_date(item.date_text)
                    reason = parsed.reason or "The date needs review."
                if parsed and parsed.status == "explicit" and parsed.value:
                    deadline_proposals.append(ProposedDeadline(
                        deadline_type=item.deadline_type,
                        due_date=parsed.value.isoformat(),
                        rule_text=(item.rule_text or item.evidence_excerpt)[:300],
                        evidence_excerpt=item.evidence_excerpt[:500],
                        verification=VerificationStatus.EXPLICIT,
                    ))
                else:
                    deadline_proposals.append(ProposedDeadline(
                        deadline_type=item.deadline_type,
                        due_date=None,
                        rule_text=(item.rule_text or item.evidence_excerpt)[:300],
                        evidence_excerpt=item.evidence_excerpt[:500],
                        verification=VerificationStatus.EXPLICIT,
                        needs_review=True,
                        review_reason=reason,
                    ))
                    unknown_fields.add(item.deadline_type.value)
                continue

            rule = parse_relative_rule(item.evidence_excerpt)
            if rule and item.rule_text and item.rule_text in item.evidence_excerpt:
                anchor_text = parsed_anchors.get(rule.anchor)
                if anchor_text:
                    anchor = date.fromisoformat(anchor_text)
                    due = compute_rule(anchor, rule.amount, rule.unit)
                    note = f"{rule.anchor.replace('_', ' ').title()} {anchor.isoformat()} + {rule.amount} {rule.unit} (anchor day counted as day 0); verify the policy interpretation."
                    deadline_proposals.append(ProposedDeadline(
                        deadline_type=item.deadline_type,
                        due_date=due.isoformat(),
                        rule_text=rule.phrase[:300],
                        evidence_excerpt=item.evidence_excerpt[:500],
                        verification=VerificationStatus.DERIVED,
                        derivation_note=note[:300],
                    ))
                else:
                    deadline_proposals.append(ProposedDeadline(
                        deadline_type=item.deadline_type,
                        due_date=None,
                        rule_text=rule.phrase[:300],
                        evidence_excerpt=item.evidence_excerpt[:500],
                        verification=VerificationStatus.EXPLICIT,
                        needs_review=True,
                        review_reason=f"The policy rule needs an anchor date ({rule.anchor.replace('_', ' ')}), which was not verified.",
                    ))
                    unknown_fields.add(item.deadline_type.value)
                continue

            deadline_proposals.append(ProposedDeadline(
                deadline_type=item.deadline_type,
                due_date=None,
                rule_text=(item.rule_text or item.evidence_excerpt)[:300],
                evidence_excerpt=item.evidence_excerpt[:500],
                verification=VerificationStatus.EXPLICIT,
                needs_review=True,
                review_reason="No supported explicit date or supported relative date rule was found.",
            ))
            unknown_fields.add(item.deadline_type.value)

        # Avoid presenting an unverified policy excerpt as supporting evidence.
        policy_evidence = next((e for e in verified_evidence if e.field_name == "policy_excerpt" and e.verification_status == VerificationStatus.EXPLICIT), None)
        policy_excerpt = candidate.policy_excerpt if policy_evidence else None
        policy_summary = candidate.policy_summary if policy_evidence else None

        review = ReviewPurchase(
            title=candidate.title,
            merchant=candidate.merchant,
            purchase_type=candidate.purchase_type,
            order_reference=candidate.order_reference,
            order_date=parsed_anchors["order_date"],
            delivery_date=parsed_anchors["delivery_date"],
            trial_start_date=parsed_anchors["trial_start_date"],
            price_text=candidate.price_text,
            policy_summary=policy_summary,
            policy_excerpt=policy_excerpt,
            unknown_fields=sorted(unknown_fields),
            source_text=safe_source,
            source_hash=digest,
            deadlines=deadline_proposals,
            evidence=verified_evidence,
        )
        diagnostics = {
            "provider": self.provider.name,
            "offline_mode": self.provider.name == "mock",
            "redacted_card_count": redacted_count,
            "source_chars": len(raw_text),
            "unknown_fields": review.unknown_fields,
            "needs_review_count": sum(1 for d in review.deadlines if d.needs_review),
        }
        return review, diagnostics
