"""Tests for human-in-the-loop review helpers."""
from pathlib import Path

from automation.core.models import UnifiedRecord
from automation.ui.review import apply_edits, load_review_records, mark_status


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




def test_apply_edits_ignores_none_values():
    record = UnifiedRecord(source="form", source_name="sample.html", customer_name="Old", email="old@example.com")
    updated = apply_edits(record, {"customer_name": None, "email": "new@example.com"})
    assert updated.customer_name == "Old"
    assert updated.email == "new@example.com"


def test_mark_status_without_note_preserves_existing_notes():
    record = UnifiedRecord(source="email", source_name="msg.eml", notes="keep me")
    flagged = mark_status(record, "approved")
    assert flagged.status == "approved"
    assert flagged.notes == "keep me"


def test_mark_status_appends_new_note_cleanly():
    record = UnifiedRecord(source="email", source_name="msg.eml")
    flagged = mark_status(record, "needs_review", note=" check spacing ")
    assert flagged.notes == "check spacing"


