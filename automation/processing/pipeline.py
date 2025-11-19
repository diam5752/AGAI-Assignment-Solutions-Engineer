"""Lightweight pipeline orchestration for the demo automation project."""
import csv
import logging
import os
from pathlib import Path
from typing import Iterable, Dict, Any, Optional

from automation.ingestion.extractors import load_records
from automation.core.models import UnifiedRecord
from automation.ingestion.quality import apply_quality_checks
from automation.reporting.sinks import push_to_google_sheets, write_excel, write_csv
from automation.reporting.templates import TEMPLATE_HEADERS, records_to_template_rows
from automation.processing.enrichment import enrich_records

from automation.core.utils import load_env_file

DEFAULT_SERVICE_ACCOUNT_PATHS = [
    Path("secrets/service_account.json"),
    Path("credentials/service_account.json"),
]
DEFAULT_SHEETS_ENV_FILE = Path("secrets/sheets.env")
_SHEETS_ENV_LOADED = False


logger = logging.getLogger(__name__)


def _ensure_sheets_env() -> None:
    """Populate Google Sheets env vars from secrets/sheets.env."""

    global _SHEETS_ENV_LOADED
    if _SHEETS_ENV_LOADED:
        return
    _SHEETS_ENV_LOADED = True

    env_path = Path(os.getenv("GOOGLE_SHEETS_ENV_FILE", DEFAULT_SHEETS_ENV_FILE))
    load_env_file(env_path)


def _default_service_account_path() -> Optional[Path]:
    for candidate in DEFAULT_SERVICE_ACCOUNT_PATHS:
        if candidate.exists():
            return candidate
    return None


def _resolve_sheets_target(
    spreadsheet_id: Optional[str],
    worksheet_title: str,
    explicit_account_path: Optional[Path],
) -> Dict[str, Any]:
    _ensure_sheets_env()
    if not spreadsheet_id:
        raise ValueError("spreadsheet_id is required when sink='sheets'")

    account_path = explicit_account_path or _default_service_account_path()
    if not account_path:
        raise ValueError(
            "Provide --service-account pointing to your Google credentials or place a file at "
            f"{DEFAULT_SERVICE_ACCOUNT_PATHS[0]}"
        )

    return {
        "spreadsheet_id": spreadsheet_id,
        "worksheet_title": worksheet_title,
        "service_account_path": account_path,
    }


def auto_sheets_target() -> Optional[Dict[str, Any]]:
    _ensure_sheets_env()
    if os.getenv("GOOGLE_SHEETS_AUTO_SYNC", "0") != "1":
        return None

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        logger.warning("Auto Sheets sync is enabled but GOOGLE_SHEETS_SPREADSHEET_ID is missing.")
        return None

    worksheet = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Sheet1")
    account_env = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT")
    account_path = Path(account_env) if account_env else _default_service_account_path()
    if not account_path:
        logger.warning("Auto Sheets sync is enabled but no service account JSON was found.")
        return None

    return {
        "spreadsheet_id": spreadsheet_id,
        "worksheet_title": worksheet,
        "service_account_path": account_path,
    }





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
    raw_records, alerts = load_records(data_dir)
    if alerts:
        logger.warning("Encountered %d ingestion alerts during loading", len(alerts))
        for alert in alerts:
            logger.warning("Alert: %s", alert)

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
    records = enrich_records(records)
    logger.info("Enriched %d records with AI-assisted summaries", len(records))
    rows = records_to_template_rows(records)
    write_csv(rows, output_path)
    logger.info("Wrote CSV output to %s", output_path)

    if sink == "excel":
        excel_target = excel_path or output_path.with_suffix(".xlsx")
        write_excel(rows, excel_target)
        logger.info("Wrote Excel output to %s", excel_target)
    elif sink == "sheets":
        sheets_target = _resolve_sheets_target(
            spreadsheet_id=spreadsheet_id,
            worksheet_title=worksheet_title,
            explicit_account_path=service_account_path,
        )
        _push_rows_to_sheets(rows, sheets_target)
    else:
        _maybe_auto_sync(rows)
    return output_path


def _push_rows_to_sheets(rows: Iterable[Dict[str, Any]], target: Dict[str, Any]) -> None:
    push_to_google_sheets(
        rows,
        spreadsheet_id=target["spreadsheet_id"],
        worksheet_title=target["worksheet_title"],
        service_account_path=target["service_account_path"],
    )


def _maybe_auto_sync(rows: Iterable[Dict[str, Any]]) -> None:
    target = auto_sheets_target()
    if not target:
        return
    _push_rows_to_sheets(rows, target)
    logger.info(
        "Pushed %d rows to Google Sheets document %s (worksheet %s)",
        len(rows),
        target["spreadsheet_id"],
        target["worksheet_title"],
    )
