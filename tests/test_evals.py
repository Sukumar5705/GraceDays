from evals.run_extraction_eval import evaluate


def test_synthetic_extraction_evaluation_has_no_negative_fabrications():
    result = evaluate()
    assert result["negative_fabrications"] == 0
    assert result["date_recall"] >= 0.90
    assert result["evidence_verification_rate"] == 1.0
    assert result["ambiguous_review_safe"] == result["ambiguous_review_cases"]
    assert result["all_cases_pass"] is True
