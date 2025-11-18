"""Mapping utilities to align unified records with the client template."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List

from automation.models import UnifiedRecord


TEMPLATE_HEADERS = [
    "Type",
    "Source",
    "Date",
    "Client_Name",
    "Email",
    "Phone",
    "Company",
    "Service_Interest",
    "Amount",
    "VAT",
    "Total_Amount",
    "Invoice_Number",
    "Priority",
    "Message",
]


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def _format_amount(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def _record_date(record: UnifiedRecord) -> str:
    return _normalize_date(record.submission_date) or _normalize_date(record.invoice_date)


def _normalize_date(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.strip()
    if "T" in text and len(text.split("T", 1)[0]) == 10:
        text = text.split("T", 1)[0]
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    try:
        parsed = parsedate_to_datetime(text)
        if parsed:
            parsed = parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed
            return parsed.date().isoformat()
    except (TypeError, ValueError):
        pass
    return text


def record_to_template_row(record: UnifiedRecord) -> Dict[str, Any]:
    """Convert a UnifiedRecord into the spreadsheet template dictionary."""

    row = {
        "Type": (record.source or "").upper(),
        "Source": _clean_text(record.source_name),
        "Date": _clean_text(_record_date(record)),
        "Client_Name": _clean_text(record.customer_name),
        "Email": record.email or "",
        "Phone": record.phone or "",
        "Company": _clean_text(record.company),
        "Service_Interest": _clean_text(record.service),
        "Amount": _format_amount(record.net_amount),
        "VAT": _format_amount(record.vat_amount),
        "Total_Amount": _format_amount(record.total_amount),
        "Invoice_Number": record.invoice_number or "",
        "Priority": record.priority or "",
        "Message": _clean_text(record.message),
    }
    return row


def records_to_template_rows(records: Iterable[UnifiedRecord]) -> List[Dict[str, Any]]:
    """Convert an iterable of UnifiedRecord objects into template-aligned rows."""

    return [record_to_template_row(record) for record in records]
