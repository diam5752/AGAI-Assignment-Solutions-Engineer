"""Lightweight pipeline orchestration for the demo automation project."""
import csv
from pathlib import Path
from typing import Iterable

from .extractors import load_records
from .models import UnifiedRecord


def ensure_output_dir(output_path: Path) -> None:
    """Create the parent directory for the output file when missing."""

    output_path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(records: Iterable[UnifiedRecord], output_path: Path) -> None:
    """Write unified records to a CSV file with consistent headers."""

    ensure_output_dir(output_path)
    rows = [record.to_dict() for record in records]
    if not rows:
        return

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(data_dir: Path, output_path: Path) -> Path:
    """Load data from dummy folders, normalize it, and emit a CSV summary."""

    records = load_records(data_dir)
    write_csv(records, output_path)
    return output_path
