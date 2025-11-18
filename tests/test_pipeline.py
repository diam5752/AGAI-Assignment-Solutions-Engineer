"""Tests for running the pipeline end-to-end into CSV outputs."""
import csv
from pathlib import Path

import pytest

from automation.extractors import load_records
from automation.pipeline import run_pipeline


def test_run_pipeline_writes_csv_with_headers_and_status(tmp_path: Path, dummy_data_dir: Path):
    output_path = tmp_path / "unified.csv"

    run_pipeline(dummy_data_dir, output_path)

    assert output_path.exists()
    rows = list(csv.DictReader(output_path.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == len(load_records(dummy_data_dir))
    assert "status" in rows[0]
    statuses = {row["status"] for row in rows}
    assert statuses.issubset({"auto_valid", "needs_review"})


def test_run_pipeline_errors_when_no_records(tmp_path: Path) -> None:
    missing_data_dir = tmp_path / "missing"
    output_path = tmp_path / "unified.csv"

    with pytest.raises(ValueError, match="No records found"):
        run_pipeline(missing_data_dir, output_path)

    assert not output_path.exists()
