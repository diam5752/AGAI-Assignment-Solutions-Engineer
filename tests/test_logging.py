"""Logging coverage to ensure errors are surfaced without stopping the run."""
from pathlib import Path

import pytest

import automation.core.pipeline as pipeline
import automation.ingestion.loader as loader


def _write_minimal_form(path: Path) -> None:
    """Create a tiny HTML form with just enough structure for the parser."""

    path.write_text(
        '<input name="full_name" value="Tester">\n'
        '<input name="email" value="tester@example.com">\n'
        '<select name="service"><option selected>Audit</option></select>',
        encoding="utf-8",
    )


def test_load_records_logs_and_continues(tmp_path: Path, caplog, monkeypatch):
    """Parsing failures should be logged and not stop other records from loading."""

    data_dir = tmp_path
    forms_dir = data_dir / "forms"
    invoices_dir = data_dir / "invoices"
    emails_dir = data_dir / "emails"
    forms_dir.mkdir()
    invoices_dir.mkdir()
    emails_dir.mkdir()

    good_form = forms_dir / "good.html"
    bad_form = forms_dir / "bad.html"
    _write_minimal_form(good_form)
    bad_form.write_text("<html>broken</html>", encoding="utf-8")

    original_parse_form = loader.parse_form

    def sometimes_failing(path: Path):
        """Raise for the bad file and delegate to the real parser otherwise."""

        if path.name == "bad.html":
            raise ValueError("boom")
        return original_parse_form(path)

    monkeypatch.setattr(loader, "parse_form", sometimes_failing)

    caplog.set_level("ERROR")
    records = loader.load_records(data_dir)

    assert len(records) == 1
    assert "bad.html" in caplog.text


def test_pipeline_logs_summary(tmp_path: Path, caplog):
    """Running the pipeline should emit a helpful summary message."""

    output_path = tmp_path / "output.csv"
    caplog.set_level("INFO")

    pipeline.run_pipeline(Path("dummy_data"), output_path)

    assert any("Wrote CSV output" in message for message in caplog.messages)
