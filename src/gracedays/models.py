from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PurchaseType(StrEnum):
    PHYSICAL_PRODUCT = "physical_product"
    SUBSCRIPTION = "subscription"
    DIGITAL_PURCHASE = "digital_purchase"
    OTHER = "other"


class PurchaseStatus(StrEnum):
    ACTIVE = "active"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    RESOLVED = "resolved"


class DeadlineType(StrEnum):
    RETURN_BY = "return_by"
    TRIAL_CANCEL_BY = "trial_cancel_by"
    RENEWAL_ON = "renewal_on"
    WARRANTY_EXPIRES = "warranty_expires"
    OTHER = "other"


class StoredDeadlineStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class VerificationStatus(StrEnum):
    EXPLICIT = "explicit"
    DERIVED = "derived"
    USER_ENTERED = "user_entered"
    UNVERIFIED = "unverified"


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid4()))
    deadline_id: str | None = None
    field_name: str = Field(min_length=1, max_length=80)
    source_excerpt: str = Field(min_length=1, max_length=600)
    verification_status: VerificationStatus
    source_hash: str = Field(min_length=64, max_length=64)


class DeadlineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid4()))
    deadline_type: DeadlineType
    due_date: str
    rule_text: str = Field(min_length=1, max_length=300)
    status: StoredDeadlineStatus = StoredDeadlineStatus.OPEN
    evidence_excerpt: str = Field(min_length=1, max_length=500)
    verification: VerificationStatus
    derivation_note: str | None = Field(default=None, max_length=300)

    @field_validator("due_date")
    @classmethod
    def valid_iso_date(cls, value: str) -> str:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("due_date must be in YYYY-MM-DD format")
        return value


class PurchaseSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=160)
    merchant: str | None = Field(default=None, max_length=120)
    purchase_type: PurchaseType = PurchaseType.PHYSICAL_PRODUCT
    order_reference: str | None = Field(default=None, max_length=80)
    order_date: str | None = None
    delivery_date: str | None = None
    trial_start_date: str | None = None
    price_text: str | None = Field(default=None, max_length=60)
    status: PurchaseStatus = PurchaseStatus.ACTIVE
    policy_summary: str | None = Field(default=None, max_length=400)
    policy_excerpt: str | None = Field(default=None, max_length=600)
    unknown_fields: list[str] = Field(default_factory=list, max_length=30)
    source_text: str = Field(default="", max_length=20_000)
    source_hash: str = Field(min_length=64, max_length=64)
    is_demo: bool = False
    deadlines: list[DeadlineInput] = Field(default_factory=list, max_length=10)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=40)

    @field_validator("order_date", "delivery_date", "trial_start_date")
    @classmethod
    def valid_optional_date(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Dates must use YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def evidence_is_verified(self) -> "PurchaseSaveRequest":
        if not self.title.strip():
            raise ValueError("title cannot be blank")
        for deadline in self.deadlines:
            if deadline.verification == VerificationStatus.UNVERIFIED:
                raise ValueError("unverified deadlines cannot be saved")
        for item in self.evidence:
            if item.verification_status == VerificationStatus.UNVERIFIED:
                raise ValueError("unverified evidence cannot be saved")
        return self


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_name: str
    source_excerpt: str


class CandidateDeadline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deadline_type: DeadlineType
    date_text: str | None = None
    evidence_excerpt: str
    rule_text: str | None = None
    rule_anchor: str | None = None
    amount: int | None = Field(default=None, ge=1, le=3650)
    unit: str | None = None


class ExtractionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    merchant: str | None = Field(default=None, max_length=120)
    purchase_type: PurchaseType = PurchaseType.PHYSICAL_PRODUCT
    order_reference: str | None = Field(default=None, max_length=80)
    order_date_text: str | None = None
    delivery_date_text: str | None = None
    trial_start_date_text: str | None = None
    price_text: str | None = Field(default=None, max_length=60)
    policy_summary: str | None = Field(default=None, max_length=400)
    policy_excerpt: str | None = Field(default=None, max_length=600)
    field_evidence: list[CandidateEvidence] = Field(default_factory=list, max_length=20)
    deadlines: list[CandidateDeadline] = Field(default_factory=list, max_length=10)
    unknown_fields: list[str] = Field(default_factory=list, max_length=30)


class ProposedDeadline(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    deadline_type: DeadlineType
    due_date: str | None = None
    rule_text: str
    evidence_excerpt: str
    verification: VerificationStatus | None = None
    needs_review: bool = False
    review_reason: str | None = None
    derivation_note: str | None = None


class EvidenceReview(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    deadline_id: str | None = None
    field_name: str
    source_excerpt: str
    verification_status: VerificationStatus
    source_hash: str


class ReviewPurchase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    merchant: str | None = None
    purchase_type: PurchaseType
    order_reference: str | None = None
    order_date: str | None = None
    delivery_date: str | None = None
    trial_start_date: str | None = None
    price_text: str | None = None
    policy_summary: str | None = None
    policy_excerpt: str | None = None
    unknown_fields: list[str] = Field(default_factory=list)
    source_text: str
    source_hash: str
    deadlines: list[ProposedDeadline] = Field(default_factory=list)
    evidence: list[EvidenceReview] = Field(default_factory=list)
    duplicate_candidates: list[dict[str, Any]] = Field(default_factory=list)

    def to_save_payload(self, is_demo: bool = False) -> dict[str, Any]:
        valid_deadlines: list[dict[str, Any]] = []
        evidence_items: list[dict[str, Any]] = []
        for deadline in self.deadlines:
            if deadline.needs_review or not deadline.due_date:
                raise ValueError(f"Deadline {deadline.deadline_type.value} needs review before saving")
            if deadline.verification is None or deadline.verification == VerificationStatus.UNVERIFIED:
                raise ValueError("Deadline evidence must be verified before saving")
            valid_deadlines.append({
                "id": deadline.id,
                "deadline_type": deadline.deadline_type.value,
                "due_date": deadline.due_date,
                "rule_text": deadline.rule_text[:300],
                "status": "open",
                "evidence_excerpt": deadline.evidence_excerpt,
                "verification": deadline.verification.value,
                "derivation_note": deadline.derivation_note,
            })
        deadline_by_type = {d.deadline_type.value: d.id for d in self.deadlines}
        for item in self.evidence:
            if item.verification_status == VerificationStatus.UNVERIFIED:
                raise ValueError(f"Evidence for {item.field_name} is unverified")
            evidence_items.append({
                "id": item.id,
                "deadline_id": item.deadline_id,
                "field_name": item.field_name,
                "source_excerpt": item.source_excerpt,
                "verification_status": item.verification_status.value,
                "source_hash": item.source_hash,
            })
        # Ensure deadline evidence is also persisted in the generic evidence table.
        known_pairs = {(e["field_name"], e["source_excerpt"]) for e in evidence_items}
        for deadline in self.deadlines:
            pair = (f"deadline:{deadline.deadline_type.value}", deadline.evidence_excerpt)
            if pair not in known_pairs:
                evidence_items.append({
                    "id": str(uuid4()),
                    "deadline_id": deadline.id,
                    "field_name": pair[0],
                    "source_excerpt": deadline.evidence_excerpt,
                    "verification_status": deadline.verification.value if deadline.verification else "unverified",
                    "source_hash": self.source_hash,
                })
        return {
            "id": self.id,
            "title": self.title.strip(),
            "merchant": self.merchant.strip() if self.merchant else None,
            "purchase_type": self.purchase_type.value,
            "order_reference": self.order_reference,
            "order_date": self.order_date,
            "delivery_date": self.delivery_date,
            "trial_start_date": self.trial_start_date,
            "price_text": self.price_text,
            "status": "active",
            "policy_summary": self.policy_summary,
            "policy_excerpt": self.policy_excerpt,
            "unknown_fields": self.unknown_fields,
            "source_text": self.source_text,
            "source_hash": self.source_hash,
            "is_demo": is_demo,
            "deadlines": valid_deadlines,
            "evidence": evidence_items,
        }
