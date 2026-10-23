from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gracedays.config import Settings
from gracedays.extraction import ExtractionService
from gracedays.providers.mock import MockProvider


def evaluate() -> dict[str, Any]:
    fixtures = json.loads((Path(__file__).resolve().parent / "fixtures" / "cases.json").read_text(encoding="utf-8"))
    service = ExtractionService(MockProvider(), Settings())
    expected_dates = 0
    matched_dates = 0
    negative_cases = 0
    negative_fabrications = 0
    evidence_total = 0
    evidence_verified = 0
    review_expected = 0
    review_safe = 0
    case_results = []

    for fixture in fixtures:
        review, _ = service.extract(fixture["source_text"])
        actual_dates = sorted({d.due_date for d in review.deadlines if d.due_date})
        expected = sorted(fixture.get("expected_due_dates", []))
        expected_dates += len(expected)
        matched_dates += len(set(expected) & set(actual_dates))
        if fixture.get("must_have_no_deadlines"):
            negative_cases += 1
            if actual_dates:
                negative_fabrications += 1
        flagged = any(d.needs_review for d in review.deadlines) or any(field in review.unknown_fields for field in ("return_by", "trial_cancel_by", "renewal_on", "warranty_expires"))
        if fixture.get("must_flag_review"):
            review_expected += 1
            if flagged:
                review_safe += 1
        for item in review.evidence:
            evidence_total += 1
            if item.source_excerpt in review.source_text and item.verification_status.value != "unverified":
                evidence_verified += 1
        case_results.append({
            "id": fixture["id"],
            "expected_dates": expected,
            "actual_dates": actual_dates,
            "needs_review_count": sum(d.needs_review for d in review.deadlines),
            "pass": set(expected).issubset(set(actual_dates)) and not (fixture.get("must_have_no_deadlines") and bool(actual_dates)) and (not fixture.get("must_flag_review") or flagged),
        })
    return {
        "fixtures": len(fixtures),
        "expected_dates": expected_dates,
        "date_recall": round(matched_dates / expected_dates, 4) if expected_dates else 1.0,
        "negative_cases": negative_cases,
        "negative_fabrications": negative_fabrications,
        "evidence_verification_rate": round(evidence_verified / evidence_total, 4) if evidence_total else 1.0,
        "ambiguous_review_cases": review_expected,
        "ambiguous_review_safe": review_safe,
        "all_cases_pass": all(row["pass"] for row in case_results),
        "cases": case_results,
    }


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["all_cases_pass"] and result["negative_fabrications"] == 0 else 1)
