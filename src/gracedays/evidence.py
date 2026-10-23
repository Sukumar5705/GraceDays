from __future__ import annotations

import hashlib
import re


_SPACE_RE = re.compile(r"\s+")


def source_hash(source_text: str) -> str:
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()


def verify_excerpt(source_text: str, excerpt: str) -> bool:
    """Only accept excerpts that are literal substrings of the original text."""
    return bool(excerpt) and excerpt in source_text


def verify_field_evidence(source_text: str, evidence: list[dict]) -> list[dict]:
    verified: list[dict] = []
    for item in evidence:
        copy = dict(item)
        copy["verified"] = verify_excerpt(source_text, str(item.get("source_excerpt", "")))
        verified.append(copy)
    return verified
