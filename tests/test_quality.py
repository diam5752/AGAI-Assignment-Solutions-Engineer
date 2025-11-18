"""Quality rules keep extracted records ready for human review."""
from pathlib import Path

from automation.extractors import parse_invoice
from automation.models import UnifiedRecord
from automation.quality import apply_quality_checks, validate_record


DATA_DIR = Path("dummy_data")


def test_validate_invoice_amounts_match():
    """Invoices should flag mismatched totals as needing review."""

    invoice_path = DATA_DIR / "invoices" / "invoice_TF-2024-001.html"
    record = parse_invoice(invoice_path)
    record.total_amount = (record.total_amount or 0) + 10  # force mismatch
    issues = validate_record(record)
    assert "net + vat does not match total" in issues


def test_apply_quality_sets_status_and_notes():
    """Quality checks should annotate records with status and notes."""

    invoice_path = DATA_DIR / "invoices" / "invoice_TF-2024-001.html"
    record = parse_invoice(invoice_path)
    reviewed = apply_quality_checks([record])[0]
    assert reviewed.status == "auto_valid"
    assert reviewed.notes and "invoice" in reviewed.notes


def test_validate_record_flags_missing_contact_details():
    record = UnifiedRecord(source="form", source_name="missing_contact.html", customer_name="Test")
    issues = validate_record(record)
    assert "contact info missing" in issues


def test_validate_record_requires_invoice_number_and_amount():
    record = UnifiedRecord(source="invoice", source_name="no_number.html", customer_name="ACME")
    issues = validate_record(record)
    assert "missing invoice number" in issues
    assert "invalid total amount" in issues


def test_apply_quality_marks_needs_review_and_appends_notes():
    record = UnifiedRecord(
        source="invoice",
        source_name="invoice.html",
        customer_name="ACME",
        invoice_number=None,
        total_amount=0,
        notes="initial",
    )

    updated = apply_quality_checks([record])[0]

    assert updated.status == "needs_review"
    assert updated.notes and "quality" in updated.notes
    assert "initial" in updated.notes
