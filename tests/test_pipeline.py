"""Tests for running the pipeline end-to-end into CSV outputs."""
import csv
from pathlib import Path

import pytest

from automation.extractors import load_records
from automation.pipeline import run_pipeline
from automation.templates import TEMPLATE_HEADERS, records_to_template_rows
from automation.models import UnifiedRecord


def test_run_pipeline_writes_csv_with_headers_and_status(tmp_path: Path, dummy_data_dir: Path):
    output_path = tmp_path / "unified.csv"

    run_pipeline(dummy_data_dir, output_path)

    assert output_path.exists()
    rows = list(csv.DictReader(output_path.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == len(load_records(dummy_data_dir))
    assert list(rows[0].keys()) == TEMPLATE_HEADERS
    assert rows[0]["Type"] in {"FORM", "EMAIL", "INVOICE"}
    assert rows[0]["Date"]


def test_run_pipeline_populates_email_dates(tmp_path: Path, dummy_data_dir: Path):
    output_path = tmp_path / "unified.csv"

    run_pipeline(dummy_data_dir, output_path)

    rows = list(csv.DictReader(output_path.read_text(encoding="utf-8").splitlines()))
    email_rows = [row for row in rows if row["Type"] == "EMAIL"]

    assert email_rows, "Expected email records in the CSV output"
    assert all(row["Date"] for row in email_rows), "Email rows should include dates"
    example_email = next(row for row in email_rows if row["Source"] == "email_01.eml")
    assert example_email["Date"] == "2024-01-20"


def test_run_pipeline_errors_when_no_records(tmp_path: Path) -> None:
    missing_data_dir = tmp_path / "missing"
    output_path = tmp_path / "unified.csv"

    with pytest.raises(ValueError, match="No records found"):
        run_pipeline(missing_data_dir, output_path)

    assert not output_path.exists()


def test_records_to_template_rows_converts_all_fields():
    record = UnifiedRecord(
        source="email",
        source_name="sample.eml",
        customer_name="  Demo   User ",
        email="demo@example.com",
        phone="+30 210 0000000",
        company=" Demo Co ",
        service="CRM Upgrade\nand support",
        message="Line one\nLine two",
        priority="high",
        submission_date="2024-01-20T12:30:00",
        invoice_number="INV-01",
        net_amount=123.4,
        vat_amount=12.34,
        total_amount=135.74,
    )

    invoice_record = UnifiedRecord(
        source="invoice",
        source_name="invoice.html",
        customer_name="Invoice Client",
        invoice_date="21/01/2024",
        invoice_number="INV-02",
    )

    rows = records_to_template_rows([record, invoice_record])

    assert list(rows[0].keys()) == TEMPLATE_HEADERS
    assert rows[0]["Type"] == "EMAIL"
    assert rows[0]["Source"] == "sample.eml"
    assert rows[0]["Client_Name"] == "Demo User"
    assert rows[0]["Company"] == "Demo Co"
    assert rows[0]["Service_Interest"] == "CRM Upgrade and support"
    assert rows[0]["Amount"] == "123.40"
    assert rows[0]["VAT"] == "12.34"
    assert rows[0]["Total_Amount"] == "135.74"
    assert rows[0]["Message"] == "Line one Line two"
    assert rows[0]["Date"] == "2024-01-20"
    assert rows[1]["Date"] == "2024-01-21"
    assert rows[1]["Type"] == "INVOICE"


def test_pipeline_output_aligns_with_template_examples(tmp_path: Path, dummy_data_dir: Path):
    """Ensure exported rows stay close to the published template samples."""

    output_path = tmp_path / "unified.csv"
    run_pipeline(dummy_data_dir, output_path)

    produced_rows = {
        row["Source"]: row
        for row in csv.DictReader(output_path.read_text(encoding="utf-8").splitlines())
    }

    template_path = dummy_data_dir / "templates" / "data_extraction_template.csv"
    template_rows = {
        row["Source"]: row
        for row in csv.DictReader(template_path.read_text(encoding="utf-8").splitlines())
    }

    # Compare representative entries from each capture channel.
    checks = {
        "contact_form_1.html": ["Service_Interest", "Priority", "Message"],
        "email_01.eml": ["Service_Interest", "Message"],
        "invoice_TF-2024-001.html": ["Amount", "VAT", "Total_Amount", "Invoice_Number"],
    }

    for source, fields in checks.items():
        assert source in produced_rows, f"Missing {source} in pipeline output"
        assert source in template_rows, f"Missing {source} in template file"

        for field in fields:
            generated = produced_rows[source][field]
            expected = template_rows[source][field]

            if field == "Message":
                assert generated.casefold().startswith(expected[:30].casefold()), f"Message drift for {source}"
            elif field == "Service_Interest":
                expected_token = expected.lower().split()[0]
                assert expected_token in generated.lower(), f"Service should align with template for {source}"
            else:
                assert generated == expected, f"Mismatch in {field} for {source}"
