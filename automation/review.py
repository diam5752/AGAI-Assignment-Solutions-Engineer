"""Helper utilities for human-in-the-loop review of extracted records."""
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List

from automation.extractors import load_records
from automation.models import UnifiedRecord
from automation.quality import apply_quality_checks


def load_review_records(data_dir: Path) -> List[UnifiedRecord]:
    """Load and validate records so the UI can present review-ready data."""

    raw_records = load_records(data_dir)
    return apply_quality_checks(raw_records)


def apply_edits(record: UnifiedRecord, updates: Dict[str, str]) -> UnifiedRecord:
    """Return a record with user-provided field updates applied."""

    # Only overwrite fields explicitly provided by the user.
    updated_fields = {key: value for key, value in updates.items() if value is not None}
    return replace(record, **updated_fields)


def mark_status(record: UnifiedRecord, status: str, note: str | None = None) -> UnifiedRecord:
    """Annotate a record with a new status and optional note."""

    merged_note = f"{record.notes or ''} {note}".strip() if note else record.notes
    return replace(record, status=status, notes=merged_note)


def records_to_rows(records: Iterable[UnifiedRecord]) -> List[Dict[str, str]]:
    """Convert records to dictionaries for tabular rendering."""

    return [record.to_dict() for record in records]
