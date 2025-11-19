"""Review helpers used by the Streamlit dashboard and other surfaces."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, List

from automation.core.models import UnifiedRecord
from automation.core.quality import apply_quality_checks
from automation.enrichment.engine import enrich_records
from automation.ingestion import get_ingestion_alerts, load_records


def load_review_records(data_dir: Path) -> tuple[List[UnifiedRecord], List[str]]:
    """Load and validate records so the UI can present review-ready data."""

    raw_records = load_records(data_dir)
    ingestion_alerts = get_ingestion_alerts()
    records = apply_quality_checks(raw_records)
    return enrich_records(records), ingestion_alerts


def apply_edits(record: UnifiedRecord, updates: Dict[str, str]) -> UnifiedRecord:
    """Return a record with user-provided field updates applied."""

    updated_fields = {key: value for key, value in updates.items() if value is not None}
    return replace(record, **updated_fields)


def mark_status(record: UnifiedRecord, status: str, note: str | None = None) -> UnifiedRecord:
    """Annotate a record with a new status and optional note."""

    merged_note = f"{record.notes or ''} {note}".strip() if note else record.notes
    return replace(record, status=status, notes=merged_note)


def records_to_rows(records: Iterable[UnifiedRecord]) -> List[Dict[str, Any]]:
    """Convert records to dictionaries for tabular rendering."""

    def _sanitize(value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.split())
        return value

    sanitized_rows = []
    for record in records:
        row = record.to_dict()
        sanitized_rows.append({key: _sanitize(value) for key, value in row.items()})
    return sanitized_rows
