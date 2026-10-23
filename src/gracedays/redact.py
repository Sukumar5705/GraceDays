from __future__ import annotations

import re

_CARDISH_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def redact_card_numbers(text: str) -> tuple[str, int]:
    """Mask Luhn-valid payment-card candidates before any provider call."""
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            count += 1
            return f"[REDACTED CARD ••••{digits[-4:]}]"
        return raw

    return _CARDISH_RE.sub(replace, text), count
