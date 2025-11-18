"""Quality rules keep extracted records ready for human review."""
from pathlib import Path

from automation.extractors import parse_invoice
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
