"""Lightweight automation package for extracting structured records."""
from automation.core import (
    TEMPLATE_HEADERS,
    UnifiedRecord,
    apply_quality_checks,
    auto_sheets_target,
    configure_logging,
    record_to_template_row,
    records_to_template_rows,
    run_pipeline,
    write_csv,
)
from automation.enrichment import enrich_records
from automation.ingestion import (
    get_ingestion_alerts,
    load_records,
    parse_email,
    parse_form,
    parse_invoice,
)
from automation.review import (
    apply_edits,
    load_review_records,
    mark_status,
    records_to_rows,
)

__all__ = [
    "TEMPLATE_HEADERS",
    "UnifiedRecord",
    "apply_quality_checks",
    "apply_edits",
    "auto_sheets_target",
    "configure_logging",
    "enrich_records",
    "get_ingestion_alerts",
    "load_records",
    "load_review_records",
    "mark_status",
    "parse_email",
    "parse_form",
    "parse_invoice",
    "record_to_template_row",
    "records_to_rows",
    "records_to_template_rows",
    "run_pipeline",
    "write_csv",
]
