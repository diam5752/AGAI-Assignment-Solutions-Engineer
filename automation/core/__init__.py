"""Core building blocks for the automation package."""
from automation.core.logging import configure_logging
from automation.core.models import UnifiedRecord
from automation.core.pipeline import auto_sheets_target, run_pipeline, write_csv
from automation.core.quality import apply_quality_checks, validate_record
from automation.core.templates import TEMPLATE_HEADERS, record_to_template_row, records_to_template_rows

__all__ = [
    "configure_logging",
    "UnifiedRecord",
    "auto_sheets_target",
    "run_pipeline",
    "write_csv",
    "apply_quality_checks",
    "validate_record",
    "TEMPLATE_HEADERS",
    "record_to_template_row",
    "records_to_template_rows",
]
