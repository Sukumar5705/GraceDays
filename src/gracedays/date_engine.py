from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from dateutil import parser
from dateutil.relativedelta import relativedelta

DateStatus = Literal["explicit", "ambiguous", "unsupported", "missing_year"]


@dataclass(frozen=True, slots=True)
class ParsedDate:
    status: DateStatus
    value: date | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RelativeRule:
    anchor: str
    amount: int
    unit: str
    phrase: str


_YEAR_RE = re.compile(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)")
_NUMERIC_DATE_RE = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-]((?:19|20|21)\d{2})\s*$")
_RELATIVE_RE = re.compile(
    r"\b(?:(?:within|for)\s+)?(?P<n>\d{1,4})\s*(?P<u>days?|weeks?|months?)\s+"
    r"(?:(?:of|from|after)\s+)?(?P<a>delivery|order|purchase|trial\s+start|activation|renewal)\b",
    re.IGNORECASE,
)


def parse_explicit_date(raw: str | None) -> ParsedDate:
    if not raw or not raw.strip():
        return ParsedDate("unsupported", reason="missing_date")
    text = raw.strip()
    if not _YEAR_RE.search(text):
        return ParsedDate("missing_year", reason="year_required")
    numeric = _NUMERIC_DATE_RE.fullmatch(text)
    if numeric:
        first, second = int(numeric.group(1)), int(numeric.group(2))
        if first <= 12 and second <= 12 and first != second:
            return ParsedDate("ambiguous", reason="day_month_order_ambiguous")
    try:
        # fuzzy=False prevents the parser from silently extracting a partial date
        # from arbitrary prose. LLM/provider output is still only a candidate.
        parsed = parser.parse(text, fuzzy=False, yearfirst=bool(re.match(r"^\d{4}-", text)))
        if parsed.year < 1900:
            return ParsedDate("unsupported", reason="year_out_of_range")
        return ParsedDate("explicit", value=parsed.date())
    except (ValueError, OverflowError, TypeError):
        return ParsedDate("unsupported", reason="unparseable_date")


def parse_relative_rule(text: str) -> RelativeRule | None:
    """Parse only narrow, explicit calendar-day/week/month rules from source text."""
    match = _RELATIVE_RE.search(text)
    if not match:
        return None
    amount = int(match.group("n"))
    if not 1 <= amount <= 3650:
        return None
    unit_token = match.group("u").lower()
    unit = "days" if unit_token.startswith("day") else "weeks" if unit_token.startswith("week") else "months"
    anchor_token = re.sub(r"\s+", " ", match.group("a").lower())
    anchor = {
        "delivery": "delivery_date",
        "order": "order_date",
        "purchase": "order_date",
        "trial start": "trial_start_date",
        "activation": "trial_start_date",
        "renewal": "order_date",
    }[anchor_token]
    return RelativeRule(anchor=anchor, amount=amount, unit=unit, phrase=match.group(0))


def compute_rule(anchor_date: date, amount: int, unit: str) -> date:
    if amount < 1 or amount > 3650:
        raise ValueError("amount must be between 1 and 3650")
    normalized = unit.lower().rstrip("s")
    if normalized == "day":
        return anchor_date + timedelta(days=amount)
    if normalized == "week":
        return anchor_date + timedelta(days=amount * 7)
    if normalized == "month":
        return anchor_date + relativedelta(months=amount)
    raise ValueError(f"Unsupported date unit: {unit}")
