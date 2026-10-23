from datetime import date

from gracedays.date_engine import compute_rule, parse_explicit_date, parse_relative_rule


def test_parse_month_date_with_year():
    parsed = parse_explicit_date("October 24, 2026")
    assert parsed.status == "explicit"
    assert parsed.value == date(2026, 10, 24)


def test_yearless_date_is_not_guessed():
    parsed = parse_explicit_date("October 24")
    assert parsed.status == "missing_year"
    assert parsed.value is None


def test_ambiguous_numeric_date_is_not_guessed():
    parsed = parse_explicit_date("03/04/2026")
    assert parsed.status == "ambiguous"
    assert parsed.value is None


def test_computes_days_and_weeks_with_anchor_day_zero():
    anchor = date(2026, 10, 20)
    assert compute_rule(anchor, 30, "days") == date(2026, 11, 19)
    assert compute_rule(anchor, 2, "weeks") == date(2026, 11, 3)


def test_month_arithmetic_clamps_at_month_end():
    assert compute_rule(date(2026, 1, 31), 1, "months") == date(2026, 2, 28)


def test_relative_rule_is_parsed_from_verbatim_text():
    rule = parse_relative_rule("Items may be returned within 30 days of delivery.")
    assert rule is not None
    assert (rule.anchor, rule.amount, rule.unit) == ("delivery_date", 30, "days")


def test_business_day_rule_is_unsupported():
    assert parse_relative_rule("Returns accepted within 5 business days of delivery.") is None
