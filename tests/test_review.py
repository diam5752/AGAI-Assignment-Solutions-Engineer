"""Tests for human-in-the-loop review helpers."""
from pathlib import Path

from automation.models import UnifiedRecord
from automation.review import apply_edits, load_review_records, mark_status, records_to_rows


def test_apply_edits_updates_fields():
    record = UnifiedRecord(source="form", source_name="sample.html", customer_name="Old")
    updated = apply_edits(record, {"customer_name": "New", "email": "a@b.com"})
    assert updated.customer_name == "New"
    assert updated.email == "a@b.com"
    # untouched fields remain as-is
    assert updated.source_name == record.source_name


def test_mark_status_appends_notes():
    record = UnifiedRecord(source="email", source_name="msg.eml", notes="existing")
    flagged = mark_status(record, "needs_review", note="check body")
    assert flagged.status == "needs_review"
    assert "existing" in (flagged.notes or "")
    assert "check body" in (flagged.notes or "")


def test_records_to_rows_matches_length(tmp_path: Path):
    records = load_review_records(Path("dummy_data"))
    rows = records_to_rows(records)
    assert len(rows) == len(records)
    assert rows[0]["source_name"] == records[0].source_name
