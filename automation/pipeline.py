"""Lightweight pipeline orchestration for the demo automation project."""
import csv
import logging
from pathlib import Path
from typing import Iterable, Dict, Any

from automation.extractors import load_records
from automation.models import UnifiedRecord
from automation.quality import apply_quality_checks
from automation.sinks import push_to_google_sheets, write_excel
from automation.templates import TEMPLATE_HEADERS, records_to_template_rows


logger = logging.getLogger(__name__)


def ensure_output_dir(output_path: Path) -> None:
    """Create the parent directory for the output file when missing."""

    output_path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(rows: Iterable[Dict[str, Any]], output_path: Path) -> None:
    """Write unified records to a CSV file with consistent headers."""

    rows = list(rows)
    ensure_output_dir(output_path)
    if not rows:
        return

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=TEMPLATE_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(
    data_dir: Path,
    output_path: Path,
    sink: str = "csv",
    spreadsheet_id: str | None = None,
    worksheet_title: str = "Sheet1",
    service_account_path: Path | None = None,
    excel_path: Path | None = None,
) -> Path:
    """Load data, add quality statuses, and emit a CSV summary."""

    logger.info("Pipeline starting for data dir %s", data_dir)
    raw_records = load_records(data_dir)
    if not raw_records:
        message = (
            f"No records found under {data_dir}. "
            "Verify the directory exists and includes forms, invoices, or emails."
        )
        logger.error(message)
        raise ValueError(message)
    logger.info("Loaded %d raw records", len(raw_records))
    records = apply_quality_checks(raw_records)
    logger.info("Annotated %d records with quality statuses", len(records))
    rows = records_to_template_rows(records)
    write_csv(rows, output_path)
    logger.info("Wrote CSV output to %s", output_path)

    if sink == "excel":
        excel_target = excel_path or output_path.with_suffix(".xlsx")
        write_excel(rows, excel_target)
        logger.info("Wrote Excel output to %s", excel_target)
    elif sink == "sheets":
        if not spreadsheet_id:
            raise ValueError("spreadsheet_id is required when sink='sheets'")
        push_to_google_sheets(
            rows,
            spreadsheet_id=spreadsheet_id,
            worksheet_title=worksheet_title,
            service_account_path=service_account_path,
        )
        logger.info(
            "Pushed %d rows to Google Sheets document %s (worksheet %s)",
            len(rows),
            spreadsheet_id,
            worksheet_title,
        )
    return output_path
