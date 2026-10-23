from gracedays.duplicates import find_duplicates


def test_duplicate_detection_by_order_reference():
    existing = [{"id": "1", "title": "Headphones", "merchant": "Store", "order_reference": "ORD-123", "order_date": "2026-10-10"}]
    result = find_duplicates({"title": "Different title", "merchant": "Store", "order_reference": "ORD-123"}, existing)
    assert len(result) == 1


def test_duplicate_detection_by_identity_and_date():
    existing = [{"id": "1", "title": "Aurora Headphones", "merchant": "Northstar", "order_reference": None, "order_date": "2026-10-10"}]
    result = find_duplicates({"title": "Aurora Headphones", "merchant": "Northstar", "order_date": "2026-10-10"}, existing)
    assert len(result) == 1
