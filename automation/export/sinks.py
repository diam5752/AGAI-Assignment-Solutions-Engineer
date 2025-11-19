"""Helper sinks for exporting unified records beyond CSV output."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List


def ensure_output_dir(output_path: Path) -> None:
    """Create parent folders for sink outputs when missing."""

    output_path.parent.mkdir(parents=True, exist_ok=True)


def push_to_google_sheets(
    rows: Iterable[Dict[str, Any]],
    spreadsheet_id: str,
    worksheet_title: str = "Sheet1",
    service_account_path: Path | None = None,
) -> None:
    """Upload rows to a Google Sheets worksheet using a service account."""

    rows = list(rows)
    if not rows:
        return

    try:
        import gspread
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("gspread is required for Google Sheets sinks") from exc

    client = (
        gspread.service_account(filename=str(service_account_path))
        if service_account_path
        else gspread.service_account()
    )
    worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_title)
    worksheet.clear()
    headers: List[str] = list(rows[0].keys())
    worksheet.append_rows([headers] + [[row.get(h, "") for h in headers] for row in rows])


def write_excel(rows: Iterable[Dict[str, Any]], output_path: Path) -> None:
    """Write rows to an Excel workbook using openpyxl."""

    rows = list(rows)
    if not rows:
        return

    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("openpyxl is required for Excel sinks") from exc

    ensure_output_dir(output_path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "unified_records"
    headers: List[str] = list(rows[0].keys())
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    workbook.save(output_path)
