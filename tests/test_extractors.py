"""Minimal tests to verify data extraction from dummy assets."""
from pathlib import Path

from automation.extractors import parse_form, parse_invoice, parse_email, load_records

DATA_DIR = Path("dummy_data")


def test_parse_form_basic_fields():
    """Ensure a contact form yields the expected name and priority."""

    form_path = DATA_DIR / "forms" / "contact_form_1.html"
    record = parse_form(form_path)
    assert record.customer_name == "Νίκος Παπαδόπουλος"
    assert record.priority == "Υψηλή"


def test_parse_invoice_amounts():
    """Extract amounts and invoice number from an invoice HTML file."""

    invoice_path = DATA_DIR / "invoices" / "invoice_TF-2024-001.html"
    record = parse_invoice(invoice_path)
    assert record.invoice_number == "TF-2024-001"
    assert record.total_amount == 1054.00
    assert record.vat_amount == 204.00


def test_parse_email_headers():
    """Validate that the email parser captures headers and body content."""

    email_path = DATA_DIR / "emails" / "email_01.eml"
    record = parse_email(email_path)
    assert "Σπύρος" in record.customer_name
    assert "CRM" in record.service
    assert "συνάντηση".casefold() in record.message.casefold()


def test_load_records_counts_all_assets():
    """Loading records should cover all files across dummy folders."""

    records = load_records(DATA_DIR)
    assert len(records) == 5 + 10 + 10
