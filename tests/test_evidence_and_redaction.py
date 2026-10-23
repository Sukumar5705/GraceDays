from gracedays.evidence import source_hash, verify_excerpt
from gracedays.redact import redact_card_numbers


def test_evidence_requires_literal_substring():
    source = "Return within 30 days of delivery."
    assert verify_excerpt(source, "within 30 days of delivery")
    assert not verify_excerpt(source, "within 90 days of delivery")
    assert not verify_excerpt(source, "Return within 30 days\nof delivery")


def test_card_number_is_redacted_before_provider_call():
    redacted, count = redact_card_numbers("Payment card 4111 1111 1111 1111 was used.")
    assert count == 1
    assert "4111 1111 1111 1111" not in redacted
    assert "REDACTED CARD" in redacted


def test_source_hash_is_stable_sha256():
    assert source_hash("example") == source_hash("example")
    assert len(source_hash("example")) == 64
