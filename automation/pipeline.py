"""Lightweight pipeline orchestration for the demo automation project."""
import csv
import logging
import os
from pathlib import Path
from typing import Iterable, Dict, Any, Optional

from automation.extractors import load_records
from automation.models import UnifiedRecord
from automation.quality import apply_quality_checks
from automation.sinks import push_to_google_sheets, write_excel
from automation.templates import TEMPLATE_HEADERS, records_to_template_rows
from automation.enrichment import enrich_records

DEFAULT_SERVICE_ACCOUNT_PATHS = [
    Path("secrets/service_account.json"),
    Path("credentials/service_account.json"),
]
DEFAULT_SHEETS_ENV_FILE = Path("secrets/sheets.env")
_SHEETS_ENV_LOADED = False


logger = logging.getLogger(__name__)


def _load_sheets_env_from_file() -> None:
    """Populate Google Sheets env vars from secrets/sheets.env."""

    global _SHEETS_ENV_LOADED
    if _SHEETS_ENV_LOADED:
        return
    _SHEETS_ENV_LOADED = True

    env_path = Path(os.getenv("GOOGLE_SHEETS_ENV_FILE", DEFAULT_SHEETS_ENV_FILE))
    if not env_path.exists():
        return

    try:
        with env_path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                os.environ[key] = value.strip().strip('"').strip("'")
    except OSError:
        logger.debug("Unable to load Google Sheets env file %s", env_path)


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
    _load_sheets_env_from_file()
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
    _load_sheets_env_from_file()
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
